"""Fleet-wide aggregation endpoints powering the data tabs."""
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.server import Server, MetricsSnapshot, Disk, NIC, ServerStatus

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


async def _latest_snapshots(db: AsyncSession):
    """Return {server_id: latest MetricsSnapshot} using DISTINCT ON — reads one row
    per server (≈ server count) instead of scanning the whole table."""
    res = await db.execute(
        select(MetricsSnapshot)
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    return {snap.server_id: snap for snap in res.scalars().all()}


@router.get("/thermal")
async def thermal_metrics(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()
    latest = await _latest_snapshots(db)
    rows = []
    for s in servers:
        snap = latest.get(s.id)
        if not snap:
            continue
        rows.append({
            "id": s.id, "hostname": s.hostname, "rack": s.rack, "rack_unit": s.rack_unit,
            "datacenter": s.datacenter, "model": s.model, "status": s.status.value if s.status else "unknown",
            "cpu_temp_avg": snap.cpu_temp_avg, "cpu_temp_max": snap.cpu_temp_max,
            "inlet_temp": snap.inlet_temp, "outlet_temp": snap.outlet_temp,
            "dimm_temp_max": snap.dimm_temp_max, "nvme_temp_max": snap.nvme_temp_max,
            "fan_count": snap.fan_count, "fan_failed_count": snap.fan_failed_count,
            "fan_speed_avg_rpm": snap.fan_speed_avg_rpm,
            "sensor_health": getattr(snap, "sensor_health", None),
            "critical_sensors": (snap.raw_sensors or {}).get("critical_sensors", []),
            "sensors": (snap.raw_sensors or {}).get("temperatures", []),
        })
    temps = [r["cpu_temp_max"] for r in rows if r["cpu_temp_max"] is not None]
    inlets = [r["inlet_temp"] for r in rows if r["inlet_temp"] is not None]
    return {
        "servers": rows,
        "summary": {
            "avg_cpu_temp": round(sum(temps) / len(temps), 1) if temps else None,
            "max_cpu_temp": max(temps) if temps else None,
            "avg_inlet_temp": round(sum(inlets) / len(inlets), 1) if inlets else None,
            "hot_count": sum(1 for t in temps if t >= 75),
            "critical_count": sum(1 for t in temps if t >= 85),
        },
        "hottest": sorted([r for r in rows if r["cpu_temp_max"] is not None],
                          key=lambda r: r["cpu_temp_max"], reverse=True)[:10],
    }


@router.get("/power")
async def power_metrics(rate_per_kwh: float = 0.12, pue: float = 1.5, db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()
    latest = await _latest_snapshots(db)
    rows = []
    total = 0.0
    total_cap = 0.0
    for s in servers:
        snap = latest.get(s.id)
        if not snap:
            continue
        w = snap.power_consumed_watts or 0
        cap = snap.power_capacity_watts or 0
        total += w
        total_cap += cap
        rows.append({
            "id": s.id, "hostname": s.hostname, "rack": s.rack,
            "status": s.status.value if s.status else "unknown",
            "power_consumed_watts": snap.power_consumed_watts,
            "power_capacity_watts": snap.power_capacity_watts,
            "power_state": snap.power_state,
            "headroom_pct": round((1 - w / cap) * 100, 1) if cap else None,
            "psu_count": snap.psu_count, "psu_failed_count": snap.psu_failed_count,
        })
    monthly_kwh = (total / 1000) * 24 * 30 * pue
    return {
        "servers": rows,
        "summary": {
            "total_watts": round(total, 1),
            "total_capacity_watts": round(total_cap, 1),
            "fleet_headroom_pct": round((1 - total / total_cap) * 100, 1) if total_cap else None,
            "monthly_kwh": round(monthly_kwh, 1),
            "monthly_cost": round(monthly_kwh * rate_per_kwh, 2),
            "rate_per_kwh": rate_per_kwh, "pue": pue,
        },
        "top_consumers": sorted([r for r in rows if r["power_consumed_watts"]],
                                key=lambda r: r["power_consumed_watts"], reverse=True)[:10],
    }


@router.get("/power/trend")
async def power_trend(hours: int = 24, db: AsyncSession = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    res = await db.execute(
        select(MetricsSnapshot.collected_at, MetricsSnapshot.power_consumed_watts)
        .where(MetricsSnapshot.collected_at >= cutoff)
        .order_by(MetricsSnapshot.collected_at.asc())
    )
    buckets = {}
    for ts, w in res.all():
        if w is None:
            continue
        key = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        buckets[key] = buckets.get(key, 0) + w
    return [{"timestamp": k, "watts": round(v, 1)} for k, v in sorted(buckets.items())]


@router.get("/storage")
async def storage_metrics(db: AsyncSession = Depends(get_db)):
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    disks = (await db.execute(select(Disk))).scalars().all()
    rows = []
    for d in disks:
        s = servers.get(d.server_id)
        rows.append({
            "id": d.id, "server_id": d.server_id,
            "hostname": s.hostname if s else "—",
            "datacenter": s.datacenter if s else None,
            "team": s.team if s else None, "family": s.family if s else None,
            "name": d.name, "model": d.model, "serial_number": d.serial_number,
            "capacity_gb": d.capacity_gb, "protocol": d.protocol, "media_type": d.media_type,
            "health": d.health, "smart_status": d.smart_status,
            "failure_predicted": d.failure_predicted, "usage_pct": d.usage_pct,
            "temperature_c": d.temperature_c,
        })
    return {
        "disks": rows,
        "summary": {
            "total_disks": len(rows),
            "healthy": sum(1 for r in rows if (r["health"] or "").upper() == "OK"),
            "predicted_failures": sum(1 for r in rows if r["failure_predicted"]),
            "total_capacity_gb": sum(r["capacity_gb"] or 0 for r in rows),
        },
    }


@router.get("/network")
async def network_metrics(db: AsyncSession = Depends(get_db)):
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    nics = (await db.execute(select(NIC))).scalars().all()
    latest = await _latest_snapshots(db)
    rows = []
    for n in nics:
        s = servers.get(n.server_id)
        snap = latest.get(n.server_id)
        rows.append({
            "id": n.id, "server_id": n.server_id,
            "hostname": s.hostname if s else "—",
            "os_ip": s.os_ip if s else None, "bmc_ip": s.bmc_ip if s else None,
            "datacenter": s.datacenter if s else None,
            "team": s.team if s else None, "family": s.family if s else None,
            "model": s.model if s else None,
            "name": n.name, "mac_address": n.mac_address, "driver": n.driver,
            "speed_gbps": n.speed_gbps, "link_status": n.link_status,
            "ip_address": n.ip_address,
            "rx_mbps": snap.net_rx_mbps if snap else None,
            "tx_mbps": snap.net_tx_mbps if snap else None,
            "errors": snap.net_errors_total if snap else None,
            "drops": snap.net_drops_total if snap else None,
        })
    return {
        "nics": rows,
        "summary": {
            "total_nics": len(rows),
            "up": sum(1 for r in rows if (r["link_status"] or "").lower() == "up"),
            "down": sum(1 for r in rows if r["link_status"] and r["link_status"].lower() != "up"),
        },
    }


@router.get("/capacity")
async def capacity_metrics(db: AsyncSession = Depends(get_db)):
    """CPU/mem/storage forecast via real linear regression over snapshot history.

    Slope is computed from actual fleet-avg hourly history. Where history/coverage
    is thin (cpu/mem only ~OS-agent servers), the metric is flagged is_estimated.
    """
    from datetime import datetime, timezone
    from app.engines.analytics import linreg_forecast

    servers = (await db.execute(select(Server))).scalars().all()
    latest = await _latest_snapshots(db)
    cpu_vals, mem_vals, disk_vals = [], [], []
    rows = []
    for s in servers:
        snap = latest.get(s.id)
        if not snap:
            continue
        if snap.cpu_usage_avg is not None:
            cpu_vals.append(snap.cpu_usage_avg)
        if snap.memory_usage_pct is not None:
            mem_vals.append(snap.memory_usage_pct)
        if snap.disk_usage_avg_pct is not None:
            disk_vals.append(snap.disk_usage_avg_pct)
        rows.append({
            "id": s.id, "hostname": s.hostname,
            "cpu_usage_avg": snap.cpu_usage_avg,
            "memory_usage_pct": snap.memory_usage_pct,
            "disk_usage_avg_pct": snap.disk_usage_avg_pct,
        })

    # Fleet-avg hourly history per metric (last 30 days) for regression
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    b = func.date_trunc("hour", MetricsSnapshot.collected_at)

    async def _hist(col):
        res = await db.execute(
            select(b, func.avg(col))
            .where(MetricsSnapshot.collected_at >= cutoff, col.isnot(None))
            .group_by(b).order_by(b)
        )
        return [(r[0], float(r[1])) for r in res.all() if r[1] is not None]

    cpu_hist = await _hist(MetricsSnapshot.cpu_usage_avg)
    mem_hist = await _hist(MetricsSnapshot.memory_usage_pct)
    disk_hist = await _hist(MetricsSnapshot.disk_usage_avg_pct)

    GROWTH_FALLBACK = {"cpu": 0.15, "memory": 0.25, "storage": 0.35}

    def _project(current, hist, key):
        """Use real linreg if >=3 points; else flag estimated + small fallback growth."""
        if len(hist) >= 3:
            fc = linreg_forecast(hist, horizon_hours=24 * 365, step_minutes=60 * 24, cap=100)
            slope_per_day = round(fc["slope_per_hour"] * 24, 4)
            def at(days):
                return round(min(max(current + slope_per_day * days, 0), 100), 1)
            return {
                "d30": at(30), "d60": at(60), "d90": at(90), "d180": at(180), "d365": at(365),
                "slope_per_day": slope_per_day, "exhaustion": fc.get("exhaustion"),
                "is_estimated": False, "datapoints": len(hist),
            }
        g = GROWTH_FALLBACK[key]
        def at(days):
            return round(min(current + g * days, 100), 1)
        return {
            "d30": at(30), "d60": at(60), "d90": at(90), "d180": at(180), "d365": at(365),
            "slope_per_day": g, "exhaustion": None,
            "is_estimated": True, "datapoints": len(hist),
        }

    avg_cpu = round(sum(cpu_vals) / len(cpu_vals), 1) if cpu_vals else 0
    avg_mem = round(sum(mem_vals) / len(mem_vals), 1) if mem_vals else 0
    avg_disk = round(sum(disk_vals) / len(disk_vals), 1) if disk_vals else 0
    return {
        "servers": rows,
        "current": {"cpu": avg_cpu, "memory": avg_mem, "storage": avg_disk},
        "coverage": {"cpu": len(cpu_vals), "memory": len(mem_vals), "storage": len(disk_vals)},
        "forecast": {
            "cpu": _project(avg_cpu, cpu_hist, "cpu"),
            "memory": _project(avg_mem, mem_hist, "memory"),
            "storage": _project(avg_disk, disk_hist, "storage"),
        },
        "note": "Forecast uses linear regression over real history where available; metrics with <3 datapoints are estimated.",
    }


@router.get("/sel")
async def sel_events(limit: int = 500, severity: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Fleet-wide System Event Log (SEL) — recent BMC events from every server's
    latest snapshot, flattened with hostname and sorted newest-first."""
    servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
    latest = await _latest_snapshots(db)

    rows = []
    servers_with_events = 0
    for sid, snap in latest.items():
        raw = snap.raw_sensors or {}
        events = raw.get("sel_events") or []
        if not isinstance(events, list) or not events:
            continue
        srv = servers.get(sid)
        servers_with_events += 1
        for e in events:
            if not isinstance(e, dict):
                continue
            sev = (e.get("severity") or "Info")
            if severity and sev.lower() != severity.lower():
                continue
            rows.append({
                "server_id": sid,
                "hostname": srv.hostname if srv else "—",
                "datacenter": srv.datacenter if srv else None,
                "team": srv.team if srv else None,
                "family": srv.family if srv else None,
                "severity": sev,
                "message": e.get("message") or e.get("Message") or "",
                "timestamp": e.get("timestamp") or e.get("created") or e.get("Created"),
                "record_id": e.get("record_id") or e.get("id"),
            })

    # Sort newest-first; events without a timestamp sink to the bottom
    rows.sort(key=lambda r: r["timestamp"] or "", reverse=True)
    sev_counts = {"Critical": 0, "Warning": 0, "Info": 0}
    for r in rows:
        k = r["severity"].capitalize() if r["severity"] else "Info"
        sev_counts[k] = sev_counts.get(k, 0) + 1
    return {
        "events": rows[:limit],
        "total": len(rows),
        "servers_with_events": servers_with_events,
        "severity_counts": sev_counts,
    }
