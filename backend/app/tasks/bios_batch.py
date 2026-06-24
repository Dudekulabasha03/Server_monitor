"""
BIOS batch-update orchestration.

Flow (per the requested workflow), for a user-supplied list of server names + a BIOS URL:
  1. Resolve each name → Server row.
  2. SSH reachability check on the OS IP.
  3. If SSH fails → PRISM refresh (updates OS IP) → re-check SSH.
  4. Credentials already default to amd/amd123 in the DB (used as-is).
  5. Flash the BIOS on every reachable server via the BIOS Provisioner API.
  6. After flashing, bulk-refresh (re-read applied BIOS from BMC).
  7. Report the latest BIOS version per server.

Runs as an in-memory job (progress pollable). Flashing live hardware is gated by the
caller requiring explicit confirmation before invoking this.
"""
from __future__ import annotations
import asyncio
import socket
import uuid
import time
from typing import Any, Dict, List, Optional
import httpx
import structlog
from sqlalchemy import select, or_

from app.database import AsyncSessionLocal
from app.models.server import Server
from app.config import settings

log = structlog.get_logger(__name__)

# In-memory job store (mirrors the BIOS API job pattern)
_JOBS: Dict[str, Dict[str, Any]] = {}


def get_batch_job(job_id: str) -> Optional[Dict[str, Any]]:
    return _JOBS.get(job_id)


def _new_job() -> str:
    jid = str(uuid.uuid4())
    _JOBS[jid] = {"job_id": jid, "status": "pending", "created": time.time(),
                  "servers": [], "summary": {}}
    return jid


async def _resolve_servers(names: List[str]) -> Dict[str, Any]:
    """Map user-supplied names/hostnames to Server rows (case-insensitive, fuzzy)."""
    found, missing = [], []
    async with AsyncSessionLocal() as db:
        for raw in names:
            n = raw.strip()
            if not n:
                continue
            s = (await db.execute(
                select(Server).where(or_(Server.hostname.ilike(n),
                                         Server.hostname.ilike(f"%{n}%")))
                .limit(1)
            )).scalar_one_or_none()
            if s:
                found.append({"id": s.id, "hostname": s.hostname, "os_ip": s.os_ip,
                              "bmc_ip": s.bmc_ip, "vendor": s.vendor.value if s.vendor else "amd_crb"})
            else:
                missing.append(n)
    return {"found": found, "missing": missing}


async def _ssh_ok(host: str, port: int = 22, timeout: float = 4.0) -> bool:
    if not host:
        return False
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


_VENDOR_MAP = {"amd_crb": "CRB", "dell": "Dell", "hpe": "HPE", "lenovo": "Lenovo", "supermicro": "SMC"}


async def _record_bios_history(server, phase: str):
    """Snapshot a server's BIOS identity (baseline before / patch after) for the
    Compliance A/B comparison. Best-effort — never blocks the batch."""
    from app.models.intelligence import BiosHistory
    try:
        async with AsyncSessionLocal() as db:
            db.add(BiosHistory(
                id=str(uuid.uuid4()), server_id=server.id, hostname=server.hostname,
                phase=phase, bios_version=server.bios_version, microcode=server.microcode,
                bmc_firmware=server.bmc_firmware,
            ))
            await db.commit()
    except Exception as e:
        log.warning("bios_history_record_failed", phase=phase, error=str(e))


async def run_bios_batch(names: List[str], bios_url: str, job_id: str,
                         do_flash: bool = True) -> None:
    """Execute the full batch workflow, recording progress into _JOBS[job_id]."""
    from app.tasks.collection import enrich_from_prism, collect_redfish_all
    job = _JOBS[job_id]
    job["status"] = "running"
    job["bios_url"] = bios_url

    resolved = await _resolve_servers(names)
    job["missing"] = resolved["missing"]
    rows = []
    for srv in resolved["found"]:
        rows.append({**srv, "ssh": None, "prism_tried": False, "flashed": False,
                     "bios_before": None, "bios_after": None, "stage": "pending", "note": ""})
    job["servers"] = rows

    BIOS_API = settings.BIOS_API_URL.rstrip("/")

    # ── Step 0: Validate the BIOS file URL up front. A broken URL would fail every
    #    flash, so check once and abort early with a clear reason if it's bad. ──
    if do_flash and bios_url:
        try:
            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                vr = (await client.post(f"{BIOS_API}/v1/bios/validate_url",
                                        data={"bios_file_url": bios_url})).json()
        except Exception as e:
            vr = {"ok": False, "reason": f"validation call failed: {e}"}
        job["url_check"] = vr
        if not vr.get("ok"):
            job["status"] = "failed"
            job["summary"] = {"total": len(rows), "flashed": 0,
                              "error": f"BIOS URL not usable: {vr.get('reason')}"}
            for r in rows:
                r["stage"] = "aborted"
                r["note"] = f"URL invalid: {vr.get('reason')}"
            log.warning("bios_batch_url_invalid", reason=vr.get("reason"), url=bios_url)
            return

    # ── Step 1-3: SSH check → PRISM refresh on fail → re-check ───────────────
    for r in rows:
        r["stage"] = "ssh-check"
        # current OS IP from DB (creds already default amd/amd123)
        async with AsyncSessionLocal() as db:
            s = (await db.execute(select(Server).where(Server.id == r["id"]))).scalar_one_or_none()
            os_ip = s.os_ip if s else r["os_ip"]
            r["bios_before"] = s.bios_version if s else None
        # Capture current config as the 'baseline' (A) before any flash happens.
        if s and do_flash:
            await _record_bios_history(s, "baseline")
        ok = await _ssh_ok(os_ip)
        if not ok:
            # SSH failed → PRISM refresh to get the latest OS IP, then re-check
            r["stage"] = "prism-refresh"
            r["prism_tried"] = True
            try:
                await enrich_from_prism(only_hostname=r["hostname"])
            except Exception as e:
                r["note"] = f"PRISM refresh failed: {e}"
            async with AsyncSessionLocal() as db:
                s = (await db.execute(select(Server).where(Server.id == r["id"]))).scalar_one_or_none()
                os_ip = s.os_ip if s else os_ip
            r["os_ip"] = os_ip
            ok = await _ssh_ok(os_ip)
        r["ssh"] = ok
        r["stage"] = "ssh-ok" if ok else "ssh-unreachable"

    # ── Step 5: Flash on every server (BMC-reachable). SSH is best-effort in the
    #    flash pipeline, so we flash even when OS SSH is down, as long as BMC works. ─
    flash_jobs = {}  # server_id -> bios-api job_id
    if do_flash:
        async with httpx.AsyncClient(timeout=60, verify=False) as client:
            for r in rows:
                async with AsyncSessionLocal() as db:
                    s = (await db.execute(select(Server).where(Server.id == r["id"]))).scalar_one_or_none()
                if not s or not s.bmc_ip:
                    r["stage"] = "skipped"; r["note"] = "no BMC IP"; continue
                r["stage"] = "flashing"
                form = {
                    "bmc_ip": s.bmc_ip, "bmc_user": s.bmc_username or "root",
                    "bmc_pwd": s.bmc_password or "0penBmc",
                    "os_ip": s.os_ip or "", "os_user": s.os_username or "amd",
                    "os_pwd": s.os_password or "amd123",
                    "vendor": _VENDOR_MAP.get(s.vendor.value if s.vendor else "amd_crb", "CRB"),
                    "bios_file_url": bios_url,
                }
                try:
                    resp = await client.post(f"{BIOS_API}/v1/bios/bios_upgrade", data=form)
                    resp.raise_for_status()
                    fjid = resp.json().get("job_id")
                    flash_jobs[r["id"]] = fjid
                    r["flash_job"] = fjid
                except Exception as e:
                    r["stage"] = "flash-failed"; r["note"] = f"flash submit failed: {e}"

        # ── Wait for flash jobs to complete (poll BIOS API) ──────────────────
        deadline = time.time() + 60 * 40  # up to 40 min for the batch
        pending = set(flash_jobs.values())
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            while pending and time.time() < deadline:
                await asyncio.sleep(20)
                done = set()
                for fjid in list(pending):
                    try:
                        jr = (await client.get(f"{BIOS_API}/jobs/{fjid}")).json()
                        st = jr.get("status")
                        if st in ("completed", "failed"):
                            done.add(fjid)
                            for r in rows:
                                if r.get("flash_job") == fjid:
                                    r["flashed"] = st == "completed"
                                    r["stage"] = "flashed" if st == "completed" else "flash-failed"
                    except Exception:
                        pass
                pending -= done

    # ── Step 6: Bulk refresh — re-read applied BIOS from BMC ──────────────────
    for r in rows:
        r["stage"] = "refreshing"
        try:
            await collect_redfish_all(only_server_id=r["id"])
        except Exception as e:
            r["note"] = (r["note"] + f" refresh failed: {e}").strip()
        async with AsyncSessionLocal() as db:
            s = (await db.execute(select(Server).where(Server.id == r["id"]))).scalar_one_or_none()
            r["bios_after"] = s.bios_version if s else None
        # Record post-refresh config as the 'patch' (B) for the A/B comparison.
        if s and r.get("flashed"):
            await _record_bios_history(s, "patch")
        r["stage"] = "done"

    job["summary"] = {
        "total": len(rows),
        "ssh_ok": sum(1 for r in rows if r["ssh"]),
        "prism_fixed": sum(1 for r in rows if r["prism_tried"] and r["ssh"]),
        "flashed": sum(1 for r in rows if r["flashed"]),
        "missing": len(resolved["missing"]),
    }
    job["status"] = "completed"
    log.info("bios_batch_done", **job["summary"])


def start_bios_batch(names: List[str], bios_url: str, do_flash: bool = True) -> str:
    """Create a job and launch the batch in the background. Returns job_id."""
    jid = _new_job()
    asyncio.create_task(run_bios_batch(names, bios_url, jid, do_flash))
    return jid
