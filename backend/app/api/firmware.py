"""Firmware compliance endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Dict, Optional
from app.database import get_db
from app.models.server import Server
from app.models.intelligence import BiosHistory
from app.engines.firmware import FirmwareCompliance

router = APIRouter(prefix="/api/v1/firmware", tags=["firmware"])


class BaselineUpdate(BaseModel):
    baseline: Dict[str, str]  # {"bios": "2.18", "bmc": "...", ...}


@router.get("/compliance")
async def compliance(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(select(Server))).scalars().all()
    engine = FirmwareCompliance()
    rows = []
    compliant_count = 0
    for s in servers:
        res = engine.evaluate(s)
        if res.compliant:
            compliant_count += 1
        rows.append({
            "id": s.id, "hostname": s.hostname, "vendor": s.vendor.value if s.vendor else None,
            "family": s.family, "team": s.team, "datacenter": s.datacenter,
            "cpu_model": s.cpu_model, "microcode": s.microcode,
            "bios_version": s.bios_version, "bmc_firmware": s.bmc_firmware,
            "compliant": res.compliant, "outdated_count": res.outdated_count,
            "items": [{"component": i.component, "current": i.current, "approved": i.approved, "compliant": i.compliant}
                      for i in res.items],
        })
    return {
        "servers": rows,
        "summary": {"total": len(rows), "compliant": compliant_count, "non_compliant": len(rows) - compliant_count},
    }


@router.get("/compare")
async def bios_compare(
    team: Optional[str] = None,
    family: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Baseline (Config A, pre-flash) vs Patch (Config B, post-flash) per server.

    For each server that has BIOS history, return the latest 'baseline' and latest
    'patch' rows (BIOS version, microcode, BMC firmware) plus per-field change flags so
    the UI can show a clean A/B diff. Filters are case-insensitive.
    """
    q = select(Server)
    if team:
        q = q.where(Server.team.ilike(team))
    if family:
        q = q.where(Server.family.ilike(family))
    servers = {s.id: s for s in (await db.execute(q)).scalars().all()}

    # Latest row per (server, phase)
    hist = (await db.execute(
        select(BiosHistory).where(BiosHistory.server_id.in_(list(servers.keys())))
        .order_by(BiosHistory.created_at.desc())
    )).scalars().all() if servers else []

    latest: Dict[str, Dict[str, BiosHistory]] = {}
    for h in hist:
        slot = latest.setdefault(h.server_id, {})
        if h.phase not in slot:  # first seen = newest (desc order)
            slot[h.phase] = h

    rows = []
    for sid, phases in latest.items():
        s = servers.get(sid)
        if not s:
            continue
        base = phases.get("baseline")
        patch = phases.get("patch")
        def _d(a, b):
            return (a or "—", b or "—", (a or None) != (b or None))
        bios_a, bios_b, bios_changed = _d(base and base.bios_version, patch and patch.bios_version)
        uc_a, uc_b, uc_changed = _d(base and base.microcode, patch and patch.microcode)
        bmc_a, bmc_b, bmc_changed = _d(base and base.bmc_firmware, patch and patch.bmc_firmware)
        rows.append({
            "id": sid, "hostname": s.hostname, "team": s.team, "family": s.family,
            "datacenter": s.datacenter,
            "baseline_bios": bios_a, "patch_bios": bios_b, "bios_changed": bios_changed,
            "baseline_microcode": uc_a, "patch_microcode": uc_b, "microcode_changed": uc_changed,
            "baseline_bmc": bmc_a, "patch_bmc": bmc_b, "bmc_changed": bmc_changed,
            "has_baseline": base is not None, "has_patch": patch is not None,
            "baseline_at": base.created_at.isoformat() if base and base.created_at else None,
            "patch_at": patch.created_at.isoformat() if patch and patch.created_at else None,
        })
    rows.sort(key=lambda r: r["hostname"])
    return {
        "servers": rows,
        "summary": {
            "total": len(rows),
            "changed": sum(1 for r in rows if r["bios_changed"] or r["microcode_changed"]),
            "awaiting_patch": sum(1 for r in rows if r["has_baseline"] and not r["has_patch"]),
        },
    }


@router.post("/{server_id}/baseline")
async def set_baseline(server_id: str, payload: BaselineUpdate, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Server not found")
    s.firmware_baseline = payload.baseline
    return {"status": "updated", "baseline": payload.baseline}
