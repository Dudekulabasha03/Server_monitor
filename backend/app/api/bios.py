"""
BIOS management endpoints — proxies to the external BIOS API server.

Patch tab  : upload a .tar.gz/.fd file or supply a URL → flash BIOS firmware.
Upgrade tab: read per-server tunable attributes, update specific settings.

All long-running operations are async (job-based). Clients poll /bios/jobs/{job_id}.
"""
from __future__ import annotations

import httpx
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.server import Server
from app.config import settings

router = APIRouter(prefix="/api/v1/bios", tags=["bios"])

# ── BIOS API server base URL (configure via BIOS_API_URL env var) ────────────
BIOS_API_URL = settings.BIOS_API_URL

# vendor string the BIOS API expects for AMD CRB boards
_VENDOR_MAP = {
    "amd_crb": "CRB",
    "dell": "Dell",
    "hpe": "HPE",
    "lenovo": "Lenovo",
    "supermicro": "SMC",
}


def _vendor(server: Server) -> str:
    raw = server.vendor.value if server.vendor else "unknown"
    return _VENDOR_MAP.get(raw, "CRB")


async def _get_server(server_id: str, db: AsyncSession) -> Server:
    s = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, f"Server {server_id!r} not found")
    return s


async def _record_bios_history(db: AsyncSession, server: Server, phase: str,
                               attributes: Optional[dict] = None):
    """Snapshot a server's BIOS identity as a baseline (pre-flash) or patch (post-flash)
    row so the Compliance tab can show a Config A vs Config B comparison."""
    import uuid as _uuid
    from app.models.intelligence import BiosHistory
    db.add(BiosHistory(
        id=str(_uuid.uuid4()), server_id=server.id, hostname=server.hostname,
        phase=phase, bios_version=server.bios_version, microcode=server.microcode,
        bmc_firmware=server.bmc_firmware, attributes=attributes,
    ))
    await db.commit()


def _require_creds(server: Server):
    """Ensure server has usable credentials, falling back to DEFAULT_OS/BMC env vars."""
    # Apply environment defaults so servers without explicit DB creds still work
    if not server.os_username:
        server.os_username = settings.DEFAULT_OS_USERNAME or "amd"
    if not server.os_password:
        server.os_password = settings.DEFAULT_OS_PASSWORD or "amd123"
    if not server.bmc_username:
        server.bmc_username = settings.DEFAULT_BMC_USERNAME or "root"
    if not server.bmc_password:
        server.bmc_password = settings.DEFAULT_BMC_PASSWORD or "0penBmc"

    missing = []
    if not server.bmc_ip:
        missing.append("bmc_ip")
    if not server.os_ip:
        missing.append("os_ip — enter it in the Creds panel or run PRISM Refresh first")
    if missing:
        raise HTTPException(422, f"Server is missing: {', '.join(missing)}")


# ── PATCH: list servers eligible for BIOS patch ───────────────────────────────

@router.get("/servers")
async def bios_servers(
    team: Optional[str] = None,
    family: Optional[str] = None,
    bios_version: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Return servers with BIOS/BMC metadata for the patch & upgrade tables.
    Supports filtering by team, CPU family, and current BIOS version.
    """
    q = select(Server)
    if team:
        q = q.where(Server.team == team)
    if family:
        q = q.where(Server.family == family)
    if bios_version:
        q = q.where(Server.bios_version == bios_version)

    servers = (await db.execute(q.order_by(Server.hostname))).scalars().all()

    rows = []
    for s in servers:
        rows.append({
            "id": s.id,
            "hostname": s.hostname,
            "bmc_ip": s.bmc_ip,
            "os_ip": s.os_ip,
            "vendor": s.vendor.value if s.vendor else None,
            "family": s.family,
            "cpu_model": s.cpu_model,
            "team": s.team,
            "bios_version": s.bios_version,
            "bmc_firmware": s.bmc_firmware,
            "microcode": s.microcode,
            "has_bmc_creds": bool(s.bmc_username and s.bmc_password),
            "has_os_creds": bool(s.os_username and s.os_password),
        })

    # distinct filter options for dropdowns
    teams = sorted({s.team for s in servers if s.team})
    families = sorted({s.family for s in servers if s.family})
    bios_versions = sorted({s.bios_version for s in servers if s.bios_version})

    return {
        "servers": rows,
        "filters": {"teams": teams, "families": families, "bios_versions": bios_versions},
        "total": len(rows),
    }


# ── Validate a BIOS file URL before flashing ──────────────────────────────────

class ValidateUrlRequest(BaseModel):
    bios_file_url: str


@router.post("/validate-url")
async def validate_bios_url(payload: ValidateUrlRequest):
    """Check whether a BIOS file URL is reachable & valid WITHOUT downloading the whole
    image. Proxies to the BIOS API's /v1/bios/validate_url."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{BIOS_API_URL}/v1/bios/validate_url",
                                  data={"bios_file_url": payload.bios_file_url})
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── Batch update: SSH-check → PRISM-fix → flash list → bulk refresh ───────────

class BatchUpdateRequest(BaseModel):
    server_names: List[str]
    bios_file_url: str
    do_flash: bool = True


@router.post("/batch-update")
async def batch_update(payload: BatchUpdateRequest):
    """Orchestrate a BIOS update across a user-supplied list of servers:
    SSH-check each → PRISM refresh on failure → re-check → flash → bulk refresh →
    report latest BIOS versions. Returns a batch job_id to poll at /bios/batch/{id}.
    """
    if not payload.server_names:
        raise HTTPException(422, "server_names is required")
    if payload.do_flash and not payload.bios_file_url:
        raise HTTPException(422, "bios_file_url is required to flash")
    from app.tasks.bios_batch import start_bios_batch
    job_id = start_bios_batch(payload.server_names, payload.bios_file_url, payload.do_flash)
    return {"batch_job_id": job_id, "servers_requested": len(payload.server_names)}


@router.get("/batch/{job_id}")
async def batch_status(job_id: str):
    """Poll a batch update job: per-server stages, SSH/PRISM/flash results, BIOS versions."""
    from app.tasks.bios_batch import get_batch_job
    job = get_batch_job(job_id)
    if not job:
        raise HTTPException(404, "Batch job not found")
    return job


# ── Refresh: re-read the applied BIOS version from the BMC for one server ──────

@router.post("/{server_id}/refresh")
async def refresh_bios_version(server_id: str, db: AsyncSession = Depends(get_db)):
    """Re-poll this server's BMC (Redfish) and update its stored BIOS version, BMC
    firmware and microcode. Use after a flash so the newly-applied BIOS shows up
    everywhere in the app (every tab reads the same Server columns).
    """
    s = await _get_server(server_id, db)
    before = {"bios_version": s.bios_version, "bmc_firmware": s.bmc_firmware,
              "microcode": s.microcode}
    # collect_redfish_all(only_server_id=...) re-reads identity (bios/bmc/microcode)
    # from the BMC and commits it to the Server row.
    from app.tasks.collection import collect_redfish_all
    try:
        result = await collect_redfish_all(only_server_id=server_id)
    except Exception as e:
        raise HTTPException(503, f"BMC poll failed: {e}")

    await db.refresh(s)
    after = {"bios_version": s.bios_version, "bmc_firmware": s.bmc_firmware,
             "microcode": s.microcode}
    # Record the post-flash version as the 'patch' (Config B) for A/B comparison.
    await _record_bios_history(db, s, "patch")
    return {
        "server_id": server_id, "hostname": s.hostname,
        "before": before, "after": after,
        "changed": before != after,
        "collect": result,
    }


# ── PATCH: get BIOS attributes for one server ─────────────────────────────────

@router.get("/{server_id}/attributes")
async def get_bios_attributes(server_id: str, db: AsyncSession = Depends(get_db)):
    """
    Read all BIOS tunable settings from the server via SCELNX_64.
    Returns: list of {Setup Question, Help String, Options, Value}.
    """
    s = await _get_server(server_id, db)
    _require_creds(s)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(
                f"{BIOS_API_URL}/v1/bios/attributes",
                params={
                    "os_ip": s.os_ip,
                    "os_user": s.os_username,
                    "os_pwd": s.os_password,
                },
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── UPGRADE: update BIOS tuning attributes ────────────────────────────────────

class TuningUpdate(BaseModel):
    attributes_to_update: List[Dict[str, str]]  # [{"Setup Question": "SVM Mode", "Value": "Enabled"}]
    reset: bool = False
    benchmark_execution_id: Optional[str] = None
    schedule_id: Optional[str] = None


@router.post("/{server_id}/update-attributes")
async def update_bios_attributes(
    server_id: str,
    payload: TuningUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update specific BIOS tuning knobs without a full firmware flash.
    Returns a job_id to poll for completion.
    """
    s = await _get_server(server_id, db)
    _require_creds(s)

    body = {
        "domain": s.fqdn or s.hostname,
        "os_ip": s.os_ip,
        "os_user": s.os_username,
        "os_pwd": s.os_password,
        "bmc_ip": s.bmc_ip,
        "bmc_user": s.bmc_username,
        "bmc_pwd": s.bmc_password,
        "reset": payload.reset,
        "attributes_to_update": payload.attributes_to_update,
        "benchmark_execution_id": payload.benchmark_execution_id,
        "schedule_id": payload.schedule_id,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{BIOS_API_URL}/v1/bios/update_attributes", json=body)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── PATCH: verify BIOS image compatibility ────────────────────────────────────

async def _apply_cred_overrides(s, db, *, os_ip=None, os_user=None, os_pwd=None,
                                bmc_ip=None, bmc_user=None, bmc_pwd=None, persist=True):
    """Apply inline OS/BMC credential overrides onto the server and optionally persist
    them so a verified-and-working set sticks for future flashes."""
    changed = False
    for attr, val in (("os_ip", os_ip), ("os_username", os_user), ("os_password", os_pwd),
                      ("bmc_ip", bmc_ip), ("bmc_username", bmc_user), ("bmc_password", bmc_pwd)):
        if val:
            setattr(s, attr, val)
            changed = True
    if changed and persist:
        await db.commit()
    return s


@router.post("/{server_id}/verify")
async def verify_bios(
    server_id: str,
    bios_file_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    os_ip: Optional[str] = Form(None),
    os_user: Optional[str] = Form(None),
    os_pwd: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Check whether a BIOS image is compatible with this server before flashing.
    Supply either a URL or upload a file. Optional os_ip/os_user/os_pwd override (and
    persist) the stored OS credentials — e.g. an IP picked from the Network tab.
    """
    s = await _get_server(server_id, db)
    await _apply_cred_overrides(s, db, os_ip=os_ip, os_user=os_user, os_pwd=os_pwd)
    _require_creds(s)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            form: Dict[str, Any] = {
                "os_ip": s.os_ip,
                "os_user": s.os_username,
                "os_pwd": s.os_password,
                "vendor": _vendor(s),
            }
            files = None
            if file:
                content = await file.read()
                files = {"file": (file.filename, content, file.content_type or "application/octet-stream")}
            elif bios_file_url:
                form["bios_file_url"] = bios_file_url

            r = await client.post(f"{BIOS_API_URL}/v1/bios/verify_bios", data=form, files=files)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── PATCH: flash BIOS firmware ────────────────────────────────────────────────

@router.post("/{server_id}/flash")
async def flash_bios(
    server_id: str,
    bios_file_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    benchmark_execution_id: Optional[str] = Form(None),
    schedule_id: Optional[str] = Form(None),
    os_ip: Optional[str] = Form(None),
    os_user: Optional[str] = Form(None),
    os_pwd: Optional[str] = Form(None),
    bmc_ip: Optional[str] = Form(None),
    bmc_user: Optional[str] = Form(None),
    bmc_pwd: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Flash BIOS firmware for one server. Supply either a URL or upload a .tar.gz/.fd.
    Optional os_*/bmc_* fields override (and persist) stored credentials.
    Returns job_id; poll /bios/jobs/{job_id} for progress and logs.
    """
    s = await _get_server(server_id, db)
    await _apply_cred_overrides(s, db, os_ip=os_ip, os_user=os_user, os_pwd=os_pwd,
                                bmc_ip=bmc_ip, bmc_user=bmc_user, bmc_pwd=bmc_pwd)
    _require_creds(s)

    # Capture the CURRENT BIOS/microcode as the 'baseline' (Config A) before flashing,
    # so the Compliance tab can later diff it against the post-flash 'patch' version.
    await _record_bios_history(db, s, "baseline")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            form: Dict[str, Any] = {
                "bmc_ip": s.bmc_ip,
                "bmc_user": s.bmc_username,
                "bmc_pwd": s.bmc_password,
                "os_ip": s.os_ip,
                "os_user": s.os_username,
                "os_pwd": s.os_password,
                "vendor": _vendor(s),
            }
            if benchmark_execution_id:
                form["benchmark_execution_id"] = benchmark_execution_id
            if schedule_id:
                form["schedule_id"] = schedule_id

            files = None
            if file:
                content = await file.read()
                files = {"file": (file.filename, content, file.content_type or "application/octet-stream")}
            elif bios_file_url:
                form["bios_file_url"] = bios_file_url
            else:
                raise HTTPException(422, "Provide either 'file' upload or 'bios_file_url'")

            r = await client.post(
                f"{BIOS_API_URL}/v1/bios/bios_upgrade",
                data=form,
                files=files,
                params={
                    "benchmark_execution_id": benchmark_execution_id or "",
                    "schedule_id": schedule_id or "",
                },
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── PATCH: bulk flash ─────────────────────────────────────────────────────────

class BulkFlashRequest(BaseModel):
    server_ids: List[str]
    bios_file_url: Optional[str] = None


@router.post("/bulk-flash")
async def bulk_flash_bios(
    payload: BulkFlashRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit flash jobs for multiple servers concurrently.
    Returns per-server {server_id, hostname, job_id, status}.
    Only URL-based flashing is supported for bulk (no multi-file upload).
    """
    if not payload.bios_file_url:
        raise HTTPException(422, "bulk-flash requires 'bios_file_url'")

    results = []
    for sid in payload.server_ids[:30]:  # safety cap
        try:
            s = await _get_server(sid, db)
            _require_creds(s)

            async with httpx.AsyncClient(timeout=30) as client:
                form: Dict[str, Any] = {
                    "bmc_ip": s.bmc_ip,
                    "bmc_user": s.bmc_username,
                    "bmc_pwd": s.bmc_password,
                    "os_ip": s.os_ip,
                    "os_user": s.os_username,
                    "os_pwd": s.os_password,
                    "vendor": _vendor(s),
                    "bios_file_url": payload.bios_file_url,
                }
                r = await client.post(f"{BIOS_API_URL}/v1/bios/bios_upgrade", data=form)
                r.raise_for_status()
                job = r.json()
                results.append({
                    "server_id": sid,
                    "hostname": s.hostname,
                    "job_id": job.get("job_id"),
                    "status": job.get("status", "pending"),
                })
        except HTTPException as e:
            results.append({"server_id": sid, "hostname": getattr(s, "hostname", sid),
                            "error": e.detail, "status": "skipped"})
        except Exception as e:
            results.append({"server_id": sid, "status": "error", "error": str(e)})

    return {"submitted": len(results), "jobs": results}


# ── RESET: factory defaults ───────────────────────────────────────────────────

@router.post("/{server_id}/reset")
async def reset_bios(server_id: str, db: AsyncSession = Depends(get_db)):
    """Reset BIOS to factory defaults via Redfish."""
    s = await _get_server(server_id, db)
    if not all([s.bmc_ip, s.bmc_username, s.bmc_password]):
        raise HTTPException(422, "BMC credentials required for reset")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            form = {
                "bmc_ip": s.bmc_ip,
                "bmc_user": s.bmc_username,
                "bmc_pwd": s.bmc_password,
                "vendor": _vendor(s),
            }
            r = await client.post(f"{BIOS_API_URL}/v1/bios/reset", data=form)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── JOB STATUS: proxy to BIOS API job store ───────────────────────────────────

@router.get("/jobs/{job_id}")
async def get_bios_job(job_id: str):
    """
    Poll BIOS operation progress.
    Returns: {job_id, status, result, logs}
    Status: pending | running | completed | failed
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BIOS_API_URL}/jobs/{job_id}")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(503, f"BIOS API unreachable: {e}")


# ── HEALTH: check BIOS API reachability ──────────────────────────────────────

@router.get("/health")
async def bios_api_health():
    """Check if the external BIOS API server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{BIOS_API_URL}/health")
            r.raise_for_status()
            return {"reachable": True, "bios_api_url": BIOS_API_URL, **r.json()}
    except Exception as e:
        return {"reachable": False, "bios_api_url": BIOS_API_URL, "error": str(e)}
