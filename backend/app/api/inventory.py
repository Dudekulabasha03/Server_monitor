"""Inventory / asset management endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from app.database import get_db
from app.models.server import Server, DimmSlot, Disk, PSU, NIC

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@router.get("")
async def list_inventory(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()
    now = datetime.now(timezone.utc)
    rows = []
    for s in servers:
        warranty_days = None
        if s.warranty_expiry:
            warranty_days = (s.warranty_expiry - now).days
        rows.append({
            "id": s.id, "hostname": s.hostname, "fqdn": s.fqdn,
            "bmc_ip": s.bmc_ip, "vendor": s.vendor.value if s.vendor else None,
            "model": s.model, "serial_number": s.serial_number, "asset_tag": s.asset_tag,
            "datacenter": s.datacenter, "rack": s.rack, "rack_unit": s.rack_unit,
            "cpu_model": s.cpu_model, "cpu_count": s.cpu_count,
            "memory_gb": s.memory_gb, "dimm_count": s.dimm_count,
            "gpu_count": s.gpu_count, "gpu_model": s.gpu_model,
            "bmc_firmware": s.bmc_firmware, "bios_version": s.bios_version,
            "os_name": s.os_name, "os_version": s.os_version,
            "environment": s.environment, "team": s.team, "project": s.project,
            "warranty_expiry": s.warranty_expiry.isoformat() if s.warranty_expiry else None,
            "warranty_days_left": warranty_days,
            "firmware_compliant": s.firmware_baseline_compliant,
            "status": s.status.value if s.status else "unknown",
        })
    return {"servers": rows, "total": len(rows)}


@router.get("/{server_id}/components")
async def server_components(server_id: str, db: AsyncSession = Depends(get_db)):
    dimms = (await db.execute(select(DimmSlot).where(DimmSlot.server_id == server_id))).scalars().all()
    disks = (await db.execute(select(Disk).where(Disk.server_id == server_id))).scalars().all()
    psus = (await db.execute(select(PSU).where(PSU.server_id == server_id))).scalars().all()
    nics = (await db.execute(select(NIC).where(NIC.server_id == server_id))).scalars().all()
    return {"dimms": dimms, "disks": disks, "psus": psus, "nics": nics}
