"""
Live monitor — on-demand sampling for server-to-server comparison.

Given a set of servers and a metric (power | temperature | cpu | memory | load), take ONE
fresh sample per server right now and return it. The frontend polls this every few seconds
to build a live-streaming comparison chart.

- cpu / memory / load  → live SSH read via the OS agent (default DB creds amd/amd123).
- power / temperature   → live BMC read via Redfish.
Unreachable servers return value=null (shown as a gap, not a guess).
"""
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models.server import Server
from app.config import settings

router = APIRouter(prefix="/api/v1/livemon", tags=["livemon"])

_SSH_METRICS = {"cpu", "memory", "load"}
_BMC_METRICS = {"power", "temperature", "temp"}


class LiveSampleRequest(BaseModel):
    server_names: List[str]
    metric: str = "cpu"  # cpu | memory | power | temperature | load


def _norm_metric(m: str) -> str:
    m = (m or "cpu").strip().lower()
    if m in ("temp", "temperature", "thermal"):
        return "temperature"
    if m in ("watt", "watts", "power"):
        return "power"
    if m in ("mem", "memory"):
        return "memory"
    if m in ("load", "loadavg"):
        return "load"
    return "cpu"


async def _resolve(names: List[str]) -> List[Server]:
    out, seen = [], set()
    async with AsyncSessionLocal() as db:
        for raw in names:
            n = raw.strip()
            if not n:
                continue
            s = (await db.execute(select(Server).where(
                or_(Server.hostname.ilike(n), Server.hostname.ilike(f"%{n}%"))).limit(1))).scalar_one_or_none()
            if s and s.id not in seen:
                seen.add(s.id)
                out.append(s)
    return out


async def _sample_ssh(s: Server, metric: str) -> Optional[float]:
    from app.collectors.os_agent import OSAgentCollector
    from app.services.credentials import OSCredentialProvider
    creds = await OSCredentialProvider().get_credentials(s.id, server=s)
    if not creds:
        return None
    host = s.os_ip or s.fqdn or s.hostname
    if not host:
        return None
    agent = OSAgentCollector(s.id, host, creds["username"], creds["password"],
                             timeout=settings.OS_AGENT_CONNECT_TIMEOUT,
                             port_check_timeout=settings.OS_AGENT_PORT_CHECK_TIMEOUT)
    m = await agent.collect()
    if m.error:
        return None
    if metric == "cpu":
        return m.cpu_usage_pct
    if metric == "memory":
        return m.memory_usage_pct
    if metric == "load":
        return m.load_1m
    return None


async def _sample_bmc(s: Server, metric: str) -> Optional[float]:
    from app.collectors.redfish_collector import RedfishCollector
    from app.services.credentials import CredentialProvider
    creds = await CredentialProvider().get_credentials(s.id, server=s)
    if not creds or not s.bmc_ip:
        return None
    try:
        async with RedfishCollector(server_id=s.id, bmc_ip=s.bmc_ip,
                                    username=creds["username"], password=creds["password"],
                                    port=s.bmc_port or 443) as c:
            rf = await c.collect_all()
    except Exception:
        return None
    if metric == "power":
        v = rf.power_consumed_watts
        return v if (v and 0 < v < 50000) else None
    if metric == "temperature":
        return max(rf.cpu_temps) if rf.cpu_temps else (rf.inlet_temp or None)
    return None


@router.post("/sample")
async def live_sample(payload: LiveSampleRequest):
    """Take one fresh live sample of `metric` for each named server (SSH or BMC)."""
    metric = _norm_metric(payload.metric)
    servers = await _resolve(payload.server_names)
    if not servers:
        raise HTTPException(404, "No matching servers")

    use_ssh = metric in _SSH_METRICS
    sampler = _sample_ssh if use_ssh else _sample_bmc

    async def one(s: Server):
        try:
            val = await asyncio.wait_for(sampler(s, metric), timeout=20)
        except Exception:
            val = None
        return {"hostname": s.hostname, "family": s.family, "team": s.team,
                "datacenter": s.datacenter, "value": val,
                "reachable": val is not None}

    results = await asyncio.gather(*[one(s) for s in servers])
    unit = {"power": "W", "temperature": "°C", "cpu": "%", "memory": "%", "load": ""}[metric]
    from datetime import datetime, timezone
    return {
        "metric": metric, "unit": unit, "source": "ssh" if use_ssh else "bmc",
        "t": datetime.now(timezone.utc).isoformat(),
        "samples": results,
        "reachable": sum(1 for r in results if r["reachable"]),
        "total": len(results),
    }
