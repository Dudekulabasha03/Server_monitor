"""
Read-only tool layer for Helios AI agents.

Every tool is a thin async wrapper over existing DB queries, returns compact JSON-able
data, and is declared as an OpenAI function schema. NOTHING here writes — agents can only
observe fleet state. This is the core guardrail.
"""
import asyncio
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, or_, String
from app.database import AsyncSessionLocal
from app.models.server import Server, MetricsSnapshot, ServerStatus, Disk, NIC
from app.models.alerts import Alert, AlertState
from app.models.intelligence import RiskScore
from app.config import settings


async def _latest_snaps(db, server_ids=None):
    q = (select(MetricsSnapshot).distinct(MetricsSnapshot.server_id)
         .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc()))
    if server_ids is not None:
        q = q.where(MetricsSnapshot.server_id.in_(server_ids))
    return {s.server_id: s for s in (await db.execute(q)).scalars().all()}


async def get_fleet_summary() -> Dict[str, Any]:
    """Fleet-wide status counts + aggregate metrics."""
    async with AsyncSessionLocal() as db:
        servers = (await db.execute(select(Server))).scalars().all()
        counts: Dict[str, int] = {}
        for s in servers:
            k = s.status.value if s.status else "unknown"
            counts[k] = counts.get(k, 0) + 1
        snaps = await _latest_snaps(db, [s.id for s in servers])
        power = sum(v.power_consumed_watts for v in snaps.values()
                    if v.power_consumed_watts and 0 < v.power_consumed_watts < 50000)
        health = [s.health_score for s in servers if s.health_score is not None]
        return {
            "total": len(servers),
            "by_status": counts,
            "total_power_watts": round(power, 1),
            "avg_health_score": round(sum(health) / len(health), 1) if health else None,
        }


async def query_servers(status: Optional[str] = None, team: Optional[str] = None,
                        family: Optional[str] = None, datacenter: Optional[str] = None,
                        search: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    """List servers matching filters with latest key metrics."""
    async with AsyncSessionLocal() as db:
        q = select(Server)
        if status:
            q = q.where(func.lower(Server.status.cast(String)) == status.lower())
        if team:
            q = q.where(Server.team.ilike(team))
        if family:
            q = q.where(Server.family.ilike(family))
        if datacenter:
            q = q.where(Server.datacenter.ilike(datacenter))
        if search:
            term = f"%{search}%"
            q = q.where(or_(
                Server.hostname.ilike(term),
                Server.cpu_model.ilike(term),
                Server.family.ilike(term),
            ))
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
        cap = min(limit, 200)
        servers = (await db.execute(q.limit(cap))).scalars().all()
        snaps = await _latest_snaps(db, [s.id for s in servers])
        rows = []
        for s in servers:
            snap = snaps.get(s.id)
            rows.append({
                "hostname": s.hostname, "status": s.status.value if s.status else "unknown",
                "family": s.family, "team": s.team, "datacenter": s.datacenter,
                "health_score": s.health_score,
                "cpu_temp_max": snap.cpu_temp_max if snap else None,
                "power_w": snap.power_consumed_watts if snap else None,
            })
        out = {"total_matching": total, "count": len(rows), "servers": rows}
        if total > len(rows):
            out["note"] = (f"{total} servers match; only the first {len(rows)} are listed. "
                           f"Use total_matching ({total}) as the true count.")
        return out


async def get_server_detail(hostname: str) -> Dict[str, Any]:
    """Full detail for one server: identity, latest snapshot, processors, components."""
    async with AsyncSessionLocal() as db:
        s = (await db.execute(select(Server).where(Server.hostname.ilike(hostname)))).scalar_one_or_none()
        if not s:
            return {"error": f"server '{hostname}' not found"}
        snap = (await db.execute(
            select(MetricsSnapshot).where(MetricsSnapshot.server_id == s.id)
            .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
        )).scalar_one_or_none()
        disks = (await db.execute(select(func.count(Disk.id)).where(Disk.server_id == s.id))).scalar()
        nics = (await db.execute(select(func.count(NIC.id)).where(NIC.server_id == s.id))).scalar()
        raw = (snap.raw_sensors or {}) if snap else {}
        return {
            "hostname": s.hostname, "status": s.status.value if s.status else "unknown",
            "family": s.family, "team": s.team, "datacenter": s.datacenter,
            "cpu_model": s.cpu_model, "sockets": s.cpu_count, "cores": s.cpu_cores_total,
            "microcode": s.microcode, "memory_gb": s.memory_gb, "health_score": s.health_score,
            "bios": s.bios_version, "bmc_firmware": s.bmc_firmware,
            "latest": {
                "cpu_temp_max": snap.cpu_temp_max if snap else None,
                "power_w": snap.power_consumed_watts if snap else None,
                "cpu_pct": snap.cpu_usage_avg if snap else None,
                "mem_pct": snap.memory_usage_pct if snap else None,
                "sensor_health": snap.sensor_health if snap else None,
                "util_bucket": snap.util_bucket if snap else None,
            } if snap else None,
            "disk_count": disks, "nic_count": nics,
            "critical_sensors": raw.get("critical_sensors", [])[:5],
            "recent_sel": raw.get("sel_events", [])[:8],
        }


async def get_alerts(severity: Optional[str] = None, hostname: Optional[str] = None,
                     limit: int = 50) -> Dict[str, Any]:
    """Firing alerts, optionally filtered by severity or host."""
    async with AsyncSessionLocal() as db:
        servers = {s.id: s.hostname for s in (await db.execute(select(Server))).scalars().all()}
        q = select(Alert).where(Alert.state == AlertState.FIRING)
        if severity:
            q = q.where(Alert.severity == severity)
        alerts = (await db.execute(q.order_by(Alert.fired_at.desc()).limit(min(limit, 200)))).scalars().all()
        rows = []
        for a in alerts:
            host = servers.get(a.server_id, "—")
            if hostname and hostname.lower() not in host.lower():
                continue
            rows.append({
                "hostname": host, "severity": a.severity.value if hasattr(a.severity, "value") else str(a.severity),
                "category": a.category.value if hasattr(a.category, "value") else str(a.category),
                "title": a.title, "message": a.message,
                "fired_at": a.fired_at.isoformat() if a.fired_at else None,
            })
        return {"count": len(rows), "alerts": rows}


async def get_sel_events(hostname: Optional[str] = None, severity: Optional[str] = None,
                         limit: int = 30) -> Dict[str, Any]:
    """Recent System Event Log entries across the fleet or for one host."""
    async with AsyncSessionLocal() as db:
        servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
        snaps = await _latest_snaps(db)
        rows = []
        for sid, snap in snaps.items():
            srv = servers.get(sid)
            if hostname and srv and hostname.lower() not in srv.hostname.lower():
                continue
            for e in (snap.raw_sensors or {}).get("sel_events", []) or []:
                if not isinstance(e, dict):
                    continue
                sev = str(e.get("severity") or "Info")
                if severity and sev.lower() != severity.lower():
                    continue
                rows.append({"hostname": srv.hostname if srv else "—", "severity": sev,
                             "message": e.get("message", ""), "timestamp": e.get("timestamp")})
        rows.sort(key=lambda r: r["timestamp"] or "", reverse=True)
        return {"count": len(rows), "events": rows[:limit]}


async def get_risk(top: int = 10) -> Dict[str, Any]:
    """Top servers by predictive risk score."""
    async with AsyncSessionLocal() as db:
        servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
        res = await db.execute(
            select(RiskScore).distinct(RiskScore.server_id)
            .order_by(RiskScore.server_id, RiskScore.scored_at.desc())
        )
        risks = list(res.scalars().all())
        risks.sort(key=lambda r: r.overall_risk or 0, reverse=True)
        rows = []
        for r in risks[:min(top, 50)]:
            s = servers.get(r.server_id)
            rows.append({"hostname": s.hostname if s else "—", "overall_risk": r.overall_risk,
                         "risk_level": r.risk_level, "factors": (r.factors or [])[:4]})
        return {"count": len(rows), "servers": rows}


_METRIC_COLS = {
    "cpu_temp": "cpu_temp_max", "temperature": "cpu_temp_max", "temp": "cpu_temp_max",
    "power": "power_consumed_watts", "watts": "power_consumed_watts",
    "cpu": "cpu_usage_avg", "cpu_usage": "cpu_usage_avg", "utilization": "cpu_usage_avg",
    "memory": "memory_usage_pct", "mem": "memory_usage_pct",
    "inlet": "inlet_temp", "disk": "disk_usage_max_pct",
}


def _resolve_metric(metric: str) -> Optional[str]:
    if not metric:
        return None
    m = metric.strip().lower().replace("%", "").replace("°c", "").strip()
    if m in _METRIC_COLS:
        return _METRIC_COLS[m]
    for k, col in _METRIC_COLS.items():
        if k in m:
            return col
    return None


async def compare_servers(hostnames: List[str], metric: str = "cpu_temp") -> Dict[str, Any]:
    """Compare a metric (temperature/power/cpu/memory) across two or more servers."""
    col = _resolve_metric(metric)
    if not col:
        return {"error": f"unknown metric '{metric}'. Use temperature/power/cpu/memory/disk."}
    async with AsyncSessionLocal() as db:
        rows = []
        for h in hostnames[:10]:
            s = (await db.execute(select(Server).where(Server.hostname.ilike(h)))).scalar_one_or_none()
            if not s:
                rows.append({"hostname": h, "error": "not found"})
                continue
            snap = (await db.execute(
                select(MetricsSnapshot).where(MetricsSnapshot.server_id == s.id)
                .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
            )).scalar_one_or_none()
            val = getattr(snap, col, None) if snap else None
            rows.append({"hostname": s.hostname, "family": s.family, "team": s.team,
                         "datacenter": s.datacenter, "status": s.status.value if s.status else "unknown",
                         "metric": metric, "value": val})
        vals = [r for r in rows if r.get("value") is not None]
        verdict = None
        if len(vals) >= 2:
            hi = max(vals, key=lambda r: r["value"])
            lo = min(vals, key=lambda r: r["value"])
            verdict = {"highest": hi["hostname"], "highest_value": hi["value"],
                       "lowest": lo["hostname"], "lowest_value": lo["value"],
                       "delta": round(hi["value"] - lo["value"], 1)}
        return {"metric": metric, "column": col, "servers": rows, "comparison": verdict}


async def top_servers_by_metric(metric: str = "cpu_temp", order: str = "desc",
                                limit: int = 10, family: Optional[str] = None,
                                team: Optional[str] = None, datacenter: Optional[str] = None) -> Dict[str, Any]:
    """Rank servers by a metric (hottest, highest power, busiest CPU/memory, etc.)."""
    col = _resolve_metric(metric)
    if not col:
        return {"error": f"unknown metric '{metric}'. Use temperature/power/cpu/memory/disk."}
    async with AsyncSessionLocal() as db:
        q = select(Server)
        if family:
            q = q.where(Server.family.ilike(family))
        if team:
            q = q.where(Server.team.ilike(team))
        if datacenter:
            q = q.where(Server.datacenter.ilike(datacenter))
        servers = (await db.execute(q)).scalars().all()
        snaps = await _latest_snaps(db, [s.id for s in servers])
        rows = []
        for s in servers:
            snap = snaps.get(s.id)
            val = getattr(snap, col, None) if snap else None
            if val is None:
                continue
            rows.append({"hostname": s.hostname, "family": s.family, "team": s.team,
                         "datacenter": s.datacenter, "value": val,
                         "status": s.status.value if s.status else "unknown"})
        rows.sort(key=lambda r: r["value"], reverse=(order != "asc"))
        return {"metric": metric, "order": order, "count": len(rows), "servers": rows[:min(limit, 50)]}


async def get_metric_history(hostname: str, metric: str = "cpu_temp", hours: int = 24) -> Dict[str, Any]:
    """Time-series history of a metric for one server (trend over N hours)."""
    from datetime import datetime, timezone, timedelta
    col = _resolve_metric(metric)
    if not col:
        return {"error": f"unknown metric '{metric}'."}
    async with AsyncSessionLocal() as db:
        s = (await db.execute(select(Server).where(Server.hostname.ilike(hostname)))).scalar_one_or_none()
        if not s:
            return {"error": f"server '{hostname}' not found"}
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        column = getattr(MetricsSnapshot, col)
        res = await db.execute(
            select(MetricsSnapshot.collected_at, column)
            .where(MetricsSnapshot.server_id == s.id, MetricsSnapshot.collected_at >= cutoff,
                   column.isnot(None))
            .order_by(MetricsSnapshot.collected_at.asc())
        )
        pts = [(t, v) for t, v in res.all() if v is not None]
        if not pts:
            return {"hostname": s.hostname, "metric": metric, "points": 0,
                    "note": "no history in window (metric may require OS-agent / unreachable BMC)"}
        vals = [v for _, v in pts]
        return {"hostname": s.hostname, "metric": metric, "hours": hours, "points": len(pts),
                "min": round(min(vals), 1), "max": round(max(vals), 1),
                "avg": round(sum(vals) / len(vals), 1),
                "first": round(vals[0], 1), "last": round(vals[-1], 1),
                "trend": "rising" if vals[-1] > vals[0] else "falling" if vals[-1] < vals[0] else "flat"}


async def get_recommendations(hostname: Optional[str] = None) -> Dict[str, Any]:
    """Active recommendations (remediation steps) for a server or fleet-wide."""
    from app.models.intelligence import Recommendation
    async with AsyncSessionLocal() as db:
        servers = {s.id: s.hostname for s in (await db.execute(select(Server))).scalars().all()}
        q = select(Recommendation).where(Recommendation.dismissed == False)  # noqa: E712
        recos = (await db.execute(q.order_by(Recommendation.created_at.desc()).limit(80))).scalars().all()
        rows = []
        for r in recos:
            host = servers.get(r.server_id, "—")
            if hostname and hostname.lower() not in host.lower():
                continue
            rows.append({"hostname": host, "severity": r.severity, "category": r.category,
                         "title": r.title, "body": r.body, "steps": r.steps or []})
        return {"count": len(rows), "recommendations": rows[:40]}


async def get_user_activity(hostname: Optional[str] = None) -> Dict[str, Any]:
    """Active user login sessions (from OS-agent SSH `who`) + idle/in-use server counts.

    Helios DOES track this via the OS agent — use this for 'who is logged in', 'user
    activity', 'active sessions', 'idle servers' questions.
    """
    from datetime import datetime, timezone
    from app.models.users import UserSession
    async with AsyncSessionLocal() as db:
        servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
        res = await db.execute(
            select(UserSession).where(UserSession.is_active == True)  # noqa: E712
            .order_by(UserSession.login_at.desc())
        )
        now = datetime.now(timezone.utc)
        sessions = []
        for s in res.scalars().all():
            login = s.login_at
            # only count freshly-reconciled sessions (matches the Users tab logic)
            if login and (now - login).total_seconds() > 600:
                continue
            srv = servers.get(s.server_id)
            if hostname and srv and hostname.lower() not in srv.hostname.lower():
                continue
            sessions.append({"hostname": srv.hostname if srv else "—",
                             "username": s.username, "session_type": s.session_type,
                             "source_ip": s.source_ip, "terminal": s.terminal,
                             "login_at": s.login_at.isoformat() if s.login_at else None})
        # idle vs in-use: a server is 'in use' if it has an active session or CPU>5%
        snaps = await _latest_snaps(db)
        active_ids = {se["hostname"] for se in sessions}
        in_use = idle = 0
        for sid, srv in servers.items():
            snap = snaps.get(sid)
            cpu = snap.cpu_usage_avg if snap else None
            has_user = srv.hostname in active_ids
            if has_user or (cpu is not None and cpu >= 5):
                in_use += 1
            elif cpu is not None:
                idle += 1
        return {"active_sessions": len(sessions), "sessions": sessions[:40],
                "servers_in_use": in_use, "servers_idle": idle,
                "note": "Sessions come from the OS agent (SSH `who`); only ~reachable hosts report."}


# Allow-list of read-only OS facts the live SSH tool may fetch. Each maps a logical
# field -> a safe, non-interactive shell command. NOTHING here mutates the host.
_OS_INFO_CMDS = {
    "os": "cat /etc/os-release 2>/dev/null | grep -E '^(PRETTY_NAME|NAME|VERSION)=' || cat /etc/redhat-release 2>/dev/null",
    "kernel": "uname -r",
    "arch": "uname -m",
    "hostname": "hostname",
    "uptime": "uptime -p 2>/dev/null || uptime",
    "smt_active": "cat /sys/devices/system/cpu/smt/active 2>/dev/null",
    "nps_numa_nodes": "numactl --hardware 2>/dev/null | grep -c '^node [0-9]* cpus:' || lscpu 2>/dev/null | grep -i 'NUMA node(s)'",
    "numa_topology": "lscpu 2>/dev/null | grep -iE 'NUMA|Socket|Core|Thread'",
    "cpu_model": "lscpu 2>/dev/null | grep -i 'Model name'",
    "memory": "free -h 2>/dev/null | head -2",
    "kernel_cmdline": "cat /proc/cmdline 2>/dev/null",
}


async def get_os_info(hostname: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """LIVE OS/kernel/NPS/SMT lookup over SSH for a specific server.

    Use this for OS distro, kernel version, NPS/NUMA, SMT, uptime, kernel cmdline —
    anything the BMC cannot see. It checks SSH reachability first, then runs read-only
    commands on the host and returns the real values. If SSH is unreachable it says so
    clearly (does NOT guess). 'fields' optionally narrows which facts to fetch; valid
    keys: os, kernel, arch, hostname, uptime, smt_active, nps_numa_nodes,
    numa_topology, cpu_model, memory, kernel_cmdline. Omit for all."""
    from app.collectors.os_agent import OSAgentCollector
    from app.services.credentials import OSCredentialProvider

    wanted = [f for f in (fields or list(_OS_INFO_CMDS)) if f in _OS_INFO_CMDS]
    if not wanted:
        wanted = list(_OS_INFO_CMDS)

    async with AsyncSessionLocal() as db:
        srv = (await db.execute(
            select(Server).where(Server.hostname.ilike(hostname))
        )).scalar_one_or_none()
        if not srv:
            srv = (await db.execute(
                select(Server).where(Server.hostname.ilike(f"%{hostname}%"))
            )).scalar_one_or_none()
        if not srv:
            return {"error": f"server '{hostname}' not found"}

        target = srv.os_ip or srv.bmc_ip
        if not srv.os_ip:
            return {"hostname": srv.hostname, "reachable": False,
                    "reason": "no OS IP on record — cannot SSH",
                    "hint": "Set the OS IP on the Network tab, then retry."}

        creds = await OSCredentialProvider().get_credentials(srv.id, server=srv)
        if not creds:
            return {"hostname": srv.hostname, "os_ip": srv.os_ip, "reachable": False,
                    "reason": "no OS credentials available for this server"}

    agent = OSAgentCollector(srv.id, srv.os_ip, creds["username"], creds["password"],
                             timeout=8, port_check_timeout=3)
    # Reachability gate first — exactly as requested: check SSH, then act.
    if not await agent._port_open():
        return {"hostname": srv.hostname, "os_ip": srv.os_ip, "reachable": False,
                "reason": "SSH port 22 unreachable (firewall/no route/host down)"}

    try:
        import asyncssh
    except ImportError:
        return {"hostname": srv.hostname, "reachable": False, "reason": "asyncssh not installed"}

    info: Dict[str, Any] = {}
    try:
        async with asyncssh.connect(
            srv.os_ip, port=22, username=creds["username"], password=creds["password"],
            known_hosts=None, connect_timeout=8,
        ) as conn:
            results = await asyncio.gather(
                *[conn.run(_OS_INFO_CMDS[f], timeout=8) for f in wanted],
                return_exceptions=True,
            )
            for f, r in zip(wanted, results):
                if isinstance(r, Exception):
                    info[f] = None
                else:
                    out = (r.stdout or "").strip()
                    info[f] = out or None
    except Exception as e:
        return {"hostname": srv.hostname, "os_ip": srv.os_ip, "reachable": False,
                "reason": f"SSH connect/auth failed: {e}"}

    return {"hostname": srv.hostname, "os_ip": srv.os_ip, "reachable": True,
            "live": True, "info": info}


async def get_network_info(hostname: Optional[str] = None, link: Optional[str] = None,
                           limit: int = 50) -> Dict[str, Any]:
    """Network: per-server NICs with IP addresses, MAC, speed, link up/down, plus the
    server's BMC IP and OS IP. Use for 'IP address', 'network', 'NIC', 'link down' questions."""
    async with AsyncSessionLocal() as db:
        servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
        nics = (await db.execute(select(NIC))).scalars().all()
        rows = []
        for n in nics:
            srv = servers.get(n.server_id)
            if hostname and srv and hostname.lower() not in srv.hostname.lower():
                continue
            up = (n.link_status or "").lower() == "up"
            if link == "up" and not up:
                continue
            if link == "down" and up:
                continue
            rows.append({"hostname": srv.hostname if srv else "—",
                         "bmc_ip": srv.bmc_ip if srv else None, "os_ip": srv.os_ip if srv else None,
                         "nic": n.name, "ip_address": n.ip_address, "mac": n.mac_address,
                         "speed_gbps": n.speed_gbps, "link": n.link_status})
        return {"count": len(rows), "nics": rows[:min(limit, 200)]}


async def get_storage_info(hostname: Optional[str] = None, limit: int = 60) -> Dict[str, Any]:
    """Storage: per-server disks (model, capacity, type, health, SMART, failure prediction)."""
    async with AsyncSessionLocal() as db:
        servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
        disks = (await db.execute(select(Disk))).scalars().all()
        rows = []
        for d in disks:
            srv = servers.get(d.server_id)
            if hostname and srv and hostname.lower() not in srv.hostname.lower():
                continue
            rows.append({"hostname": srv.hostname if srv else "—",
                         "disk": d.name, "model": d.model, "capacity_gb": d.capacity_gb,
                         "type": d.media_type or d.protocol, "health": d.health,
                         "smart": d.smart_status, "failure_predicted": d.failure_predicted})
        predicted = sum(1 for r in rows if r["failure_predicted"])
        return {"count": len(rows), "predicted_failures": predicted, "disks": rows[:min(limit, 200)]}


async def get_firmware_info(hostname: Optional[str] = None, limit: int = 80) -> Dict[str, Any]:
    """Firmware/microcode per server: BIOS, BMC firmware, CPU microcode, family."""
    async with AsyncSessionLocal() as db:
        q = select(Server)
        if hostname:
            q = q.where(Server.hostname.ilike(f"%{hostname}%"))
        servers = (await db.execute(q.limit(min(limit, 300)))).scalars().all()
        rows = [{"hostname": s.hostname, "family": s.family, "cpu_model": s.cpu_model,
                 "microcode": s.microcode, "bios": s.bios_version, "bmc_firmware": s.bmc_firmware}
                for s in servers]
        return {"count": len(rows), "servers": rows}


async def get_bios_update_status(
    team: Optional[str] = None,
    family: Optional[str] = None,
    bios_version: Optional[str] = None,
    limit: int = 60,
) -> Dict[str, Any]:
    """
    BIOS patch & upgrade readiness: per-server BIOS version, BMC version, credential status,
    and whether they can be patched/tuned via the BIOS API. Use for questions about BIOS
    versions, which servers need BIOS updates, tuning readiness, or bulk flash eligibility.
    """
    async with AsyncSessionLocal() as db:
        q = select(Server)
        if team:
            q = q.where(Server.team.ilike(team))
        if family:
            q = q.where(Server.family.ilike(family))
        if bios_version:
            q = q.where(Server.bios_version.ilike(f"%{bios_version}%"))
        servers = (await db.execute(q.limit(min(limit, 300)))).scalars().all()

        rows = []
        bios_versions: Dict[str, int] = {}
        for s in servers:
            bv = s.bios_version or "unknown"
            bios_versions[bv] = bios_versions.get(bv, 0) + 1
            has_bmc_creds = bool(s.bmc_username and s.bmc_password)
            has_os_creds = bool(s.os_username and s.os_password)
            rows.append({
                "hostname": s.hostname,
                "family": s.family,
                "team": s.team,
                "bios_version": s.bios_version,
                "bmc_firmware": s.bmc_firmware,
                "microcode": s.microcode,
                "has_bmc_creds": has_bmc_creds,
                "has_os_creds": has_os_creds,
                "patch_ready": has_bmc_creds and has_os_creds and bool(s.bmc_ip) and bool(s.os_ip),
            })

        patch_ready = sum(1 for r in rows if r["patch_ready"])
        return {
            "count": len(rows),
            "patch_ready": patch_ready,
            "missing_creds": len(rows) - patch_ready,
            "bios_version_distribution": bios_versions,
            "servers": rows,
        }


async def validate_bios_url(bios_file_url: str) -> Dict[str, Any]:
    """Check whether a BIOS file URL is reachable & valid WITHOUT downloading the whole
    image. Use this BEFORE flashing, or when a flash failed, to tell the user if the URL
    works and why not (bad extension, HTTP error, SMB unresolved/auth, etc.)."""
    import httpx as _httpx
    base = settings.BIOS_API_URL.rstrip("/")
    try:
        async with _httpx.AsyncClient(timeout=30, verify=False) as client:
            r = await client.post(f"{base}/v1/bios/validate_url",
                                  data={"bios_file_url": bios_file_url})
            return r.json()
    except Exception as e:
        return {"ok": False, "reason": f"validation failed: {e}", "url": bios_file_url}


async def start_bios_batch_update(server_names: List[str], bios_file_url: str,
                                  confirm: bool = False) -> Dict[str, Any]:
    """Start a BIOS batch update across a list of servers (SSH-check → PRISM-fix on
    failure → flash → bulk refresh → report versions). REQUIRES confirm=true — this
    flashes live hardware and reboots servers. If confirm is false, returns a preview
    asking the user to confirm (human-in-the-loop)."""
    if not server_names:
        return {"error": "no server names provided"}
    # Resolve preview first
    async with AsyncSessionLocal() as db:
        matched, missing = [], []
        for raw in server_names:
            n = raw.strip()
            if not n:
                continue
            s = (await db.execute(select(Server).where(
                Server.hostname.ilike(f"%{n}%")).limit(1))).scalar_one_or_none()
            (matched.append(s.hostname) if s else missing.append(n))
    # Validate the BIOS file URL up front so we never ask the user to confirm a flash
    # that would fail on a broken/unreachable URL.
    url_check = await validate_bios_url(bios_file_url)
    if not confirm:
        if not url_check.get("ok"):
            return {"requires_confirmation": False, "url_ok": False,
                    "url_check": url_check, "matched_servers": matched, "unmatched": missing,
                    "message": (f"⚠ The BIOS file URL is NOT usable: {url_check.get('reason')}. "
                                f"Fix the URL or use a reachable http(s):// link (or a local upload) "
                                f"before flashing. I won't proceed until the URL works.")}
        return {"requires_confirmation": True, "url_ok": True, "url_check": url_check,
                "action": "BIOS batch flash + reboot",
                "matched_servers": matched, "unmatched": missing,
                "bios_file_url": bios_file_url,
                "message": (f"BIOS file URL is valid ({url_check.get('reason')}). This will FLASH "
                            f"BIOS and REBOOT {len(matched)} server(s): {', '.join(matched[:20])}. "
                            f"Reply to confirm to proceed.")}
    if not url_check.get("ok"):
        return {"started": False, "url_ok": False, "url_check": url_check,
                "message": f"Aborted — BIOS URL not usable: {url_check.get('reason')}."}
    from app.tasks.bios_batch import start_bios_batch
    job_id = start_bios_batch(server_names, bios_file_url, do_flash=True)
    return {"started": True, "batch_job_id": job_id,
            "matched_servers": matched, "unmatched": missing,
            "note": "Poll batch status with get_bios_batch_status."}


async def live_compare(server_names: List[str], metric: str = "cpu") -> Dict[str, Any]:
    """Take a LIVE sample (SSH for cpu/memory/load, BMC for power/temperature) of a metric
    across servers for comparison RIGHT NOW. Returns current values + a deep-link to the
    live-streaming monitor page. Use for 'compare live power/temp/cpu/memory across X, Y'."""
    from app.api.livemon import _resolve, _norm_metric, _sample_ssh, _sample_bmc, _SSH_METRICS
    import asyncio as _a
    m = _norm_metric(metric)
    servers = await _resolve(server_names)
    if not servers:
        return {"error": "no matching servers"}
    sampler = _sample_ssh if m in _SSH_METRICS else _sample_bmc
    async def one(s):
        try:
            v = await _a.wait_for(sampler(s, m), timeout=20)
        except Exception:
            v = None
        return {"hostname": s.hostname, "value": v, "reachable": v is not None}
    samples = await _a.gather(*[one(s) for s in servers])
    unit = {"power": "W", "temperature": "°C", "cpu": "%", "memory": "%", "load": ""}[m]
    link = "/livemon?servers=" + ",".join(s.hostname for s in servers) + f"&metric={m}"
    return {"metric": m, "unit": unit, "source": "ssh" if m in _SSH_METRICS else "bmc",
            "samples": samples, "live_monitor_link": link,
            "note": "Values are live. Open live_monitor_link for a streaming comparison chart."}


async def get_bios_batch_status(batch_job_id: str) -> Dict[str, Any]:
    """Check progress of a BIOS batch update: per-server stage, SSH/PRISM/flash, versions."""
    from app.tasks.bios_batch import get_batch_job
    job = get_batch_job(batch_job_id)
    if not job:
        return {"error": "batch job not found"}
    return {"status": job.get("status"), "summary": job.get("summary"),
            "servers": [{"hostname": r["hostname"], "stage": r["stage"], "ssh": r["ssh"],
                         "flashed": r["flashed"], "bios_before": r["bios_before"],
                         "bios_after": r["bios_after"], "note": r["note"]}
                        for r in job.get("servers", [])],
            "missing": job.get("missing", [])}


# ── Tool registry: name → (callable, OpenAI function schema) ────────────────────
TOOLS = {
    "get_fleet_summary": (get_fleet_summary, {
        "type": "function", "function": {
            "name": "get_fleet_summary",
            "description": "Get fleet-wide status counts, total power, and average health score.",
            "parameters": {"type": "object", "properties": {}},
        }}),
    "query_servers": (query_servers, {
        "type": "function", "function": {
            "name": "query_servers",
            "description": "List servers matching filters with latest metrics. All filters are case-insensitive. "
                           "team/family/datacenter match the named fields (e.g. family='Turin', team='TSP'). "
                           "Use 'search' for a CPU model number or partial text (e.g. '9755', '9655') — it matches "
                           "hostname, cpu_model, and family. Combine filters, e.g. team='TSP' + family='Turin' for "
                           "'how many Turin servers in TSP', or search='9755' for 'how many servers have a 9755'.",
            "parameters": {"type": "object", "properties": {
                "status": {"type": "string", "enum": ["healthy", "warning", "at_risk", "critical", "offline", "unknown"]},
                "team": {"type": "string"}, "family": {"type": "string"},
                "datacenter": {"type": "string"}, "search": {"type": "string"},
                "limit": {"type": "integer"},
            }},
        }}),
    "get_server_detail": (get_server_detail, {
        "type": "function", "function": {
            "name": "get_server_detail",
            "description": "Full detail for one server by hostname: hardware, latest telemetry, sensors, recent SEL.",
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string"}}, "required": ["hostname"]},
        }}),
    "get_alerts": (get_alerts, {
        "type": "function", "function": {
            "name": "get_alerts",
            "description": "List currently firing alerts, optionally by severity or hostname.",
            "parameters": {"type": "object", "properties": {
                "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                "hostname": {"type": "string"}, "limit": {"type": "integer"}}},
        }}),
    "get_sel_events": (get_sel_events, {
        "type": "function", "function": {
            "name": "get_sel_events",
            "description": "Recent System Event Log (SEL) entries, fleet-wide or for one host.",
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string"},
                "severity": {"type": "string", "enum": ["Critical", "Warning", "Info"]},
                "limit": {"type": "integer"}}},
        }}),
    "get_risk": (get_risk, {
        "type": "function", "function": {
            "name": "get_risk",
            "description": "Top servers ranked by predictive risk score.",
            "parameters": {"type": "object", "properties": {"top": {"type": "integer"}}},
        }}),
    "compare_servers": (compare_servers, {
        "type": "function", "function": {
            "name": "compare_servers",
            "description": "Compare a metric across 2+ servers side-by-side. Use for 'compare X vs Y temperature/power/cpu/memory' questions.",
            "parameters": {"type": "object", "properties": {
                "hostnames": {"type": "array", "items": {"type": "string"}},
                "metric": {"type": "string", "description": "temperature | power | cpu | memory | disk | inlet"}},
                "required": ["hostnames"]},
        }}),
    "top_servers_by_metric": (top_servers_by_metric, {
        "type": "function", "function": {
            "name": "top_servers_by_metric",
            "description": "Rank servers by a metric — hottest, highest power, busiest CPU/memory. Filter by family/team/datacenter.",
            "parameters": {"type": "object", "properties": {
                "metric": {"type": "string", "description": "temperature | power | cpu | memory | disk"},
                "order": {"type": "string", "enum": ["desc", "asc"]},
                "limit": {"type": "integer"}, "family": {"type": "string"},
                "team": {"type": "string"}, "datacenter": {"type": "string"}}},
        }}),
    "get_metric_history": (get_metric_history, {
        "type": "function", "function": {
            "name": "get_metric_history",
            "description": "Trend of a metric over N hours for one server (min/max/avg/first/last/trend). Use for 'how has X's temperature changed' questions.",
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string"},
                "metric": {"type": "string", "description": "temperature | power | cpu | memory | disk"},
                "hours": {"type": "integer"}}, "required": ["hostname"]},
        }}),
    "get_recommendations": (get_recommendations, {
        "type": "function", "function": {
            "name": "get_recommendations",
            "description": "Active remediation recommendations (with steps) for a server or fleet-wide.",
            "parameters": {"type": "object", "properties": {"hostname": {"type": "string"}}},
        }}),
    "get_user_activity": (get_user_activity, {
        "type": "function", "function": {
            "name": "get_user_activity",
            "description": "Active user login sessions (OS-agent SSH) + idle/in-use server counts. Use for 'user activity', 'who is logged in', 'active sessions', 'idle servers'.",
            "parameters": {"type": "object", "properties": {"hostname": {"type": "string"}}},
        }}),
    "get_network_info": (get_network_info, {
        "type": "function", "function": {
            "name": "get_network_info",
            "description": "Per-server network: NIC IP addresses, MAC, speed, link up/down, plus BMC IP and OS IP. Use for 'IP address', 'network', 'NIC', 'link down' questions.",
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string"},
                "link": {"type": "string", "enum": ["up", "down"]},
                "limit": {"type": "integer"}}},
        }}),
    "get_storage_info": (get_storage_info, {
        "type": "function", "function": {
            "name": "get_storage_info",
            "description": "Per-server disks: model, capacity, type, health, SMART status, failure prediction. Use for storage/disk questions.",
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string"}, "limit": {"type": "integer"}}},
        }}),
    "get_firmware_info": (get_firmware_info, {
        "type": "function", "function": {
            "name": "get_firmware_info",
            "description": "Per-server firmware: BIOS version, BMC firmware, CPU microcode, family. Use for firmware/microcode/BIOS questions.",
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string"}, "limit": {"type": "integer"}}},
        }}),
    "get_os_info": (get_os_info, {
        "type": "function", "function": {
            "name": "get_os_info",
            "description": (
                "LIVE OS-level lookup over SSH for ONE server. Use this for OS distro / "
                "operating system, kernel version, NPS / NUMA nodes, SMT (hyperthreading), "
                "uptime, kernel cmdline — anything the BMC cannot expose. It first checks "
                "SSH reachability, then runs read-only commands on the host and returns the "
                "REAL values. If SSH is unreachable it reports that clearly instead of "
                "guessing. ALWAYS prefer this over saying 'OS info is not available' — "
                "actually try it. Requires a specific hostname."),
            "parameters": {"type": "object", "properties": {
                "hostname": {"type": "string", "description": "Exact or partial server hostname"},
                "fields": {"type": "array", "items": {"type": "string"},
                           "description": "Optional subset: os, kernel, arch, hostname, uptime, "
                                          "smt_active, nps_numa_nodes, numa_topology, cpu_model, "
                                          "memory, kernel_cmdline. Omit for all."}},
                "required": ["hostname"]},
        }}),
    "get_bios_update_status": (get_bios_update_status, {
        "type": "function", "function": {
            "name": "get_bios_update_status",
            "description": (
                "BIOS patch & upgrade readiness per server: BIOS version distribution, BMC firmware, "
                "credential status, and whether each server can be patched or tuned via the BIOS management API. "
                "Use for questions about 'BIOS update', 'which servers need BIOS', 'BIOS versions', "
                "'bulk flash eligibility', 'tuning readiness', or 'how many servers have BIOS X'."
            ),
            "parameters": {"type": "object", "properties": {
                "team": {"type": "string"},
                "family": {"type": "string"},
                "bios_version": {"type": "string", "description": "Filter to servers with this exact BIOS version"},
                "limit": {"type": "integer"},
            }},
        }}),
    "validate_bios_url": (validate_bios_url, {
        "type": "function", "function": {
            "name": "validate_bios_url",
            "description": ("Check if a BIOS file URL is reachable and valid WITHOUT downloading the "
                            "full image. Use before flashing or when a URL/flash isn't working — "
                            "returns ok + a reason (bad extension, HTTP error, SMB unresolved/auth)."),
            "parameters": {"type": "object", "properties": {
                "bios_file_url": {"type": "string"}}, "required": ["bios_file_url"]},
        }}),
    "start_bios_batch_update": (start_bios_batch_update, {
        "type": "function", "function": {
            "name": "start_bios_batch_update",
            "description": ("Start a BIOS batch update across a list of servers given a BIOS file URL. "
                            "Workflow: SSH-check each, PRISM-refresh IP if SSH fails, re-check, flash BIOS, "
                            "bulk-refresh, report new versions. ALWAYS call first with confirm=false to "
                            "preview affected servers, then confirm=true only after the user explicitly "
                            "approves (this reboots live hardware)."),
            "parameters": {"type": "object", "properties": {
                "server_names": {"type": "array", "items": {"type": "string"}},
                "bios_file_url": {"type": "string"},
                "confirm": {"type": "boolean"}},
                "required": ["server_names", "bios_file_url"]},
        }}),
    "get_bios_batch_status": (get_bios_batch_status, {
        "type": "function", "function": {
            "name": "get_bios_batch_status",
            "description": "Check progress/result of a BIOS batch update by batch_job_id.",
            "parameters": {"type": "object", "properties": {
                "batch_job_id": {"type": "string"}}, "required": ["batch_job_id"]},
        }}),
    "live_compare": (live_compare, {
        "type": "function", "function": {
            "name": "live_compare",
            "description": ("Take a LIVE sample of a metric across servers RIGHT NOW for comparison — "
                            "SSH for cpu/memory/load, BMC Redfish for power/temperature. Use when the user "
                            "asks to check/compare LIVE power, temperature, CPU or memory across servers. "
                            "Returns current values + a deep-link to the streaming live-monitor chart."),
            "parameters": {"type": "object", "properties": {
                "server_names": {"type": "array", "items": {"type": "string"}},
                "metric": {"type": "string", "description": "cpu | memory | power | temperature | load"}},
                "required": ["server_names"]},
        }}),
}


def tool_schemas(names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    names = names or list(TOOLS.keys())
    return [TOOLS[n][1] for n in names if n in TOOLS]


async def run_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'"}
    fn = TOOLS[name][0]
    try:
        return await fn(**(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"{name} failed: {e}"}
