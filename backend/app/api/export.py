"""
CSV/Excel export endpoints for all major data views.
Supports filters so the download matches exactly what the user sees on screen.
"""
import csv
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.database import get_db
from app.models.server import Server, MetricsSnapshot, Disk, NIC
from app.models.alerts import Alert
from app.core.rbac import get_current_user
from app.models.auth import AuthUser

router = APIRouter(prefix="/export", tags=["export"])


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Convert list of dicts to CSV streaming response with correct Excel headers."""
    output = io.StringIO()

    if not rows:
        output.write("No data available for the selected filters\n")
    else:
        writer = csv.DictWriter(
            output,
            fieldnames=rows[0].keys(),
            quoting=csv.QUOTE_ALL,      # quote every field — Excel handles this best
            lineterminator="\r\n",      # CRLF for Windows Excel compatibility
        )
        writer.writeheader()
        writer.writerows(rows)

    content = output.getvalue()
    # Prepend UTF-8 BOM so Excel auto-detects encoding without conversion wizard
    bom_content = "﻿" + content

    return StreamingResponse(
        iter([bom_content.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/csv; charset=utf-8",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


def _ts(dt) -> str:
    if dt is None:
        return ""
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


# ── Servers / Inventory ───────────────────────────────────────────────────────

@router.get("/servers")
async def export_servers(
    team:       Optional[str] = None,
    status:     Optional[str] = None,
    datacenter: Optional[str] = None,
    family:     Optional[str] = None,
    search:     Optional[str] = None,
    fmt:        str = Query("csv", regex="^(csv|excel)$"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthUser = Depends(get_current_user),
):
    """Export server inventory with current metrics."""
    q = select(Server)
    if team:        q = q.where(Server.team == team)
    if status:      q = q.where(Server.status == status)
    if datacenter:  q = q.where(Server.datacenter == datacenter)
    if family:      q = q.where(Server.family.ilike(f"%{family}%"))
    if search:      q = q.where(Server.hostname.ilike(f"%{search}%"))
    # Scope non-admins to their team
    if current_user.role == "user":
        from app.api.auth import _TEAM_MAP_REVERSE
        pass  # handled by frontend passing team param

    result = await db.execute(q.order_by(Server.team, Server.hostname))
    servers = result.scalars().all()

    # Get latest snapshots
    if servers:
        snap_res = await db.execute(
            select(MetricsSnapshot)
            .distinct(MetricsSnapshot.server_id)
            .where(MetricsSnapshot.server_id.in_([s.id for s in servers]))
            .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
        )
        snap_map = {s.server_id: s for s in snap_res.scalars().all()}
    else:
        snap_map = {}

    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    rows = []
    for s in servers:
        snap = snap_map.get(s.id)
        rows.append({
            "Hostname":      s.hostname,
            "Status":        s.status.value if hasattr(s.status, "value") else s.status,
            "Team":          s.team or "",
            "Family":        s.family or "",
            "Datacenter":    s.datacenter or "",
            "Rack":          s.rack or "",
            "Vendor":        s.vendor or "",
            "Model":         s.model or "",
            "CPU_Model":     s.cpu_model or "",
            "CPU_Count":     s.cpu_count or "",
            "Memory_GB":     s.memory_gb or "",
            "BMC_IP":        s.bmc_ip or "",
            "OS_IP":         s.os_ip or "",
            "OS_Type":       s.os_type or "",
            "BIOS_Version":  s.bios_version or "",
            "BMC_Firmware":  s.bmc_firmware or "",
            "Health_Score":  s.health_score or "",
            "CPU_Temp_Max":  round(snap.cpu_temp_max, 1) if snap and snap.cpu_temp_max else "",
            "Power_W":       round(snap.power_consumed_watts, 0) if snap and snap.power_consumed_watts else "",
            "CPU_Usage_Pct": round(snap.cpu_usage_avg, 1) if snap and snap.cpu_usage_avg else "",
            "Mem_Usage_Pct": round(snap.memory_usage_pct, 1) if snap and snap.memory_usage_pct else "",
            "Last_Seen":     _ts(s.last_seen),
            "Environment":   s.environment or "",
            "BIOS_Compliant": s.firmware_baseline_compliant if s.firmware_baseline_compliant is not None else "",
        })

    return _csv_response(rows, f"servers_{now_ts}.csv")


# ── Network / NICs ────────────────────────────────────────────────────────────

@router.get("/network")
async def export_network(
    team:       Optional[str] = None,
    link_status: Optional[str] = None,
    datacenter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    q = select(NIC, Server).join(Server, NIC.server_id == Server.id)
    if team:        q = q.where(Server.team == team)
    if datacenter:  q = q.where(Server.datacenter == datacenter)
    if link_status: q = q.where(NIC.link_status == link_status)
    q = q.order_by(Server.team, Server.hostname)

    result = await db.execute(q)
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for nic, server in result:
        rows.append({
            "Hostname":    server.hostname,
            "Team":        server.team or "",
            "Datacenter":  server.datacenter or "",
            "NIC_Name":    nic.name or "",
            "MAC_Address": nic.mac_address or "",
            "Speed_Gbps":  nic.speed_gbps or "",
            "Link_Status": nic.link_status or "",
            "IP_Address":  nic.ip_address or "",
            "Driver":      nic.driver or "",
            "Firmware":    nic.firmware_version or "",
            "BMC_IP":      server.bmc_ip or "",
            "OS_IP":       server.os_ip or "",
        })

    return _csv_response(rows, f"network_{now_ts}.csv")


# ── Storage / Disks ───────────────────────────────────────────────────────────

@router.get("/storage")
async def export_storage(
    team:       Optional[str] = None,
    health:     Optional[str] = None,
    datacenter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    q = select(Disk, Server).join(Server, Disk.server_id == Server.id)
    if team:       q = q.where(Server.team == team)
    if datacenter: q = q.where(Server.datacenter == datacenter)
    if health:     q = q.where(Disk.health == health)
    q = q.order_by(Server.team, Server.hostname)

    result = await db.execute(q)
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for disk, server in result:
        rows.append({
            "Hostname":          server.hostname,
            "Team":              server.team or "",
            "Datacenter":        server.datacenter or "",
            "Slot":              disk.slot or "",
            "Model":             disk.model or "",
            "Type":              disk.disk_type or "",
            "Capacity_GB":       disk.capacity_gb or "",
            "Health":            disk.health or "",
            "Failure_Predicted": disk.failure_predicted if disk.failure_predicted is not None else "",
            "SMART_Status":      disk.smart_status or "",
            "Firmware":          disk.firmware_version or "",
            "Serial":            disk.serial_number or "",
            "Temperature_C":     disk.temperature_c or "",
            "Power_On_Hours":    disk.power_on_hours or "",
        })

    return _csv_response(rows, f"storage_{now_ts}.csv")


# ── BIOS Compliance ───────────────────────────────────────────────────────────

@router.get("/compliance")
async def export_compliance(
    team:       Optional[str] = None,
    family:     Optional[str] = None,
    compliant:  Optional[bool] = None,
    datacenter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    q = select(Server)
    if team:       q = q.where(Server.team == team)
    if datacenter: q = q.where(Server.datacenter == datacenter)
    if family:     q = q.where(Server.family.ilike(f"%{family}%"))
    if compliant is not None:
        q = q.where(Server.firmware_baseline_compliant == compliant)
    q = q.order_by(Server.firmware_baseline_compliant.asc().nulls_last(), Server.team, Server.hostname)

    result = await db.execute(q)
    servers = result.scalars().all()
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

    rows = []
    for s in servers:
        rows.append({
            "Hostname":          s.hostname,
            "Team":              s.team or "",
            "Family":            s.family or "",
            "Datacenter":        s.datacenter or "",
            "BIOS_Version":      s.bios_version or "",
            "BIOS_Baseline":     s.firmware_baseline or "",
            "Compliant":         "Yes" if s.firmware_baseline_compliant is True else ("No" if s.firmware_baseline_compliant is False else "Unknown"),
            "BMC_Firmware":      s.bmc_firmware or "",
            "Microcode":         str(s.microcode) if s.microcode else "",
            "Last_Seen":         _ts(s.last_seen),
        })

    return _csv_response(rows, f"bios_compliance_{now_ts}.csv")


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def export_alerts(
    team:     Optional[str] = None,
    severity: Optional[str] = None,
    state:    Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    q = select(Alert, Server).join(Server, Alert.server_id == Server.id)
    if team:     q = q.where(Server.team == team)
    if severity: q = q.where(Alert.severity == severity)
    if state:    q = q.where(Alert.state == state)
    q = q.order_by(Alert.fired_at.desc())

    result = await db.execute(q)
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for alert, server in result:
        rows.append({
            "Server":       server.hostname,
            "Team":         server.team or "",
            "Datacenter":   server.datacenter or "",
            "Title":        alert.title or "",
            "Severity":     str(alert.severity.value) if hasattr(alert.severity, "value") else str(alert.severity),
            "Category":     str(alert.category.value) if hasattr(alert.category, "value") else str(alert.category),
            "State":        str(alert.state.value) if hasattr(alert.state, "value") else str(alert.state),
            "Message":      alert.message or "",
            "Fired_At":     _ts(alert.fired_at),
            "Resolved_At":  _ts(alert.resolved_at),
        })

    return _csv_response(rows, f"alerts_{now_ts}.csv")


# ── Changelog ─────────────────────────────────────────────────────────────────

@router.get("/changelog")
async def export_changelog(
    team:       Optional[str] = None,
    datacenter: Optional[str] = None,
    hours:      int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    # Use raw SQL to avoid ORM enum/column mismatch issues
    team_filter = f"AND s.team = '{team}'" if team else ""
    dc_filter = f"AND s.datacenter = '{datacenter}'" if datacenter else ""
    rows_raw = await db.execute(text(
        f"SELECT s.hostname, s.team, s.datacenter, "
        f"ce.kind, ce.old_value, ce.new_value, ce.created_at "
        f"FROM change_events ce JOIN servers s ON ce.server_id = s.id "
        f"WHERE ce.created_at >= NOW() - INTERVAL '{hours} hours' "
        f"{team_filter} {dc_filter} "
        f"ORDER BY ce.created_at DESC LIMIT 5000"
    ))
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for row in rows_raw:
        rows.append({
            "Server":      row[0],
            "Team":        row[1] or "",
            "Datacenter":  row[2] or "",
            "Change_Type": row[3] or "",
            "Old_Value":   row[4] or "",
            "New_Value":   row[5] or "",
            "Occurred_At": _ts(row[6]),
        })

    return _csv_response(rows, f"changelog_{now_ts}.csv")


# ── User Activity (sessions) ──────────────────────────────────────────────────

@router.get("/user-activity")
async def export_user_activity(
    team: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    from app.models.users import UserSession
    q = select(UserSession, Server).join(Server, UserSession.server_id == Server.id)
    if team: q = q.where(Server.team == team)
    q = q.order_by(UserSession.login_at.desc()).limit(5000)

    result = await db.execute(q)
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for session, server in result:
        rows.append({
            "Server":        server.hostname,
            "Team":          server.team or "",
            "Datacenter":    server.datacenter or "",
            "Username":      session.username or "",
            "Full_Name":     session.full_name or "",
            "Email":         session.email or "",
            "User_Team":     session.team or "",
            "Session_Type":  session.session_type or "",
            "Source_IP":     session.source_ip or "",
            "Login_At":      _ts(session.login_at),
            "Logout_At":     _ts(session.logout_at),
            "Duration_Sec":  session.duration_seconds or "",
            "CPU_Avg_Pct":   round(session.cpu_avg_pct, 1) if session.cpu_avg_pct else "",
            "Mem_Avg_Pct":   round(session.memory_avg_pct, 1) if session.memory_avg_pct else "",
            "Is_Active":     "Yes" if session.is_active else "No",
        })

    return _csv_response(rows, f"user_activity_{now_ts}.csv")


# ── Reservations ──────────────────────────────────────────────────────────────

@router.get("/reservations")
async def export_reservations(
    team:        Optional[str] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    from app.api.reservations import ServerReservation
    from sqlalchemy import and_
    q = select(ServerReservation, Server).join(Server, ServerReservation.server_id == Server.id)
    if team: q = q.where(ServerReservation.team == team)
    if active_only: q = q.where(ServerReservation.is_active == True)  # noqa: E712
    q = q.order_by(ServerReservation.reserved_at.desc()).limit(5000)

    result = await db.execute(q)
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for res, server in result:
        rows.append({
            "Server":         server.hostname,
            "Server_Team":    server.team or "",
            "Datacenter":     server.datacenter or "",
            "Family":         server.family or "",
            "User_Email":     res.user_email or "",
            "User_Name":      res.user_name or "",
            "User_Team":      res.team or "",
            "Purpose":        res.purpose or "",
            "Benchmark":      res.benchmark_name or "",
            "Status":         res.status or "",
            "Reserved_At":    _ts(res.reserved_at),
            "Expires_At":     _ts(res.expires_at),
            "Released_At":    _ts(res.released_at),
            "Result_URL":     res.result_url or "",
            "Notes":          res.notes or "",
        })

    return _csv_response(rows, f"reservations_{now_ts}.csv")


# ── Usage Report ──────────────────────────────────────────────────────────────

@router.get("/usage-report")
async def export_usage_report(
    team: Optional[str] = None,
    days: int = Query(7, le=90),
    db: AsyncSession = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
):
    from app.api.reservations import ServerReservation
    q = select(
        ServerReservation.user_email,
        ServerReservation.user_name,
        ServerReservation.team,
        ServerReservation.benchmark_name,
        ServerReservation.purpose,
        ServerReservation.status,
        ServerReservation.reserved_at,
        ServerReservation.released_at,
        ServerReservation.expires_at,
        Server.hostname,
        Server.family,
        Server.datacenter,
    ).join(Server, ServerReservation.server_id == Server.id)

    from sqlalchemy import func
    q = q.where(ServerReservation.reserved_at >= func.now() - text(f"interval '{days} days'"))
    if team: q = q.where(ServerReservation.team == team)
    q = q.order_by(ServerReservation.reserved_at.desc())

    result = await db.execute(q)
    rows = []
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for row in result:
        end = row.released_at or row.expires_at
        hours = round((end - row.reserved_at).total_seconds() / 3600, 1) if end and row.reserved_at else ""
        rows.append({
            "User_Email":   row.user_email,
            "User_Name":    row.user_name or "",
            "User_Team":    row.team or "",
            "Server":       row.hostname,
            "Family":       row.family or "",
            "Datacenter":   row.datacenter or "",
            "Purpose":      row.purpose or "",
            "Benchmark":    row.benchmark_name or "",
            "Status":       row.status or "",
            "Reserved_At":  _ts(row.reserved_at),
            "Duration_Hrs": hours,
        })

    return _csv_response(rows, f"usage_report_{days}d_{now_ts}.csv")
