"""Rack visualization endpoints — servers grouped by datacenter -> rack -> U."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.server import Server, MetricsSnapshot

router = APIRouter(prefix="/api/v1/racks", tags=["racks"])


@router.get("")
async def list_racks(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()

    res = await db.execute(
        select(MetricsSnapshot)
        .distinct(MetricsSnapshot.server_id)
        .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
    )
    snaps = {snap.server_id: snap for snap in res.scalars().all()}

    # Group: datacenter -> rack -> list of servers
    datacenters: dict = {}
    for s in servers:
        dc = s.datacenter or "Unassigned"
        rack = s.rack or "Unassigned"
        snap = snaps.get(s.id)
        datacenters.setdefault(dc, {}).setdefault(rack, []).append({
            "id": s.id, "hostname": s.hostname, "rack_unit": s.rack_unit,
            "rack_unit_size": s.rack_unit_size or 1,
            "status": s.status.value if s.status else "unknown",
            "health_score": s.health_score,
            "cpu_temp_max": snap.cpu_temp_max if snap else None,
            "power_consumed_watts": snap.power_consumed_watts if snap else None,
            "model": s.model, "family": s.family, "team": s.team,
            "vendor": s.vendor.value if s.vendor else None,
        })

    out = []
    for dc, racks in datacenters.items():
        rack_list = []
        for rack_name, srvs in racks.items():
            temps = [s["cpu_temp_max"] for s in srvs if s["cpu_temp_max"] is not None]
            power = [s["power_consumed_watts"] for s in srvs if s["power_consumed_watts"]]
            rack_list.append({
                "rack": rack_name,
                "servers": sorted(srvs, key=lambda x: x["rack_unit"] or 0, reverse=True),
                "server_count": len(srvs),
                "avg_temp": round(sum(temps) / len(temps), 1) if temps else None,
                "total_power": round(sum(power), 1) if power else None,
                "critical_count": sum(1 for s in srvs if s["status"] == "critical"),
            })
        out.append({"datacenter": dc, "racks": sorted(rack_list, key=lambda r: r["rack"])})
    return {"datacenters": out}
