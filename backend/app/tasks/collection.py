"""
Collection task orchestration — ties collectors → DB → health → alerts.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, delete
import structlog

from app.database import AsyncSessionLocal
from app.models.server import Server, MetricsSnapshot, ServerStatus, DimmSlot, Disk, PSU, NIC
from app.models.health import HealthScore
from app.models.alerts import Alert, AlertState
from app.collectors.redfish_collector import FleetRedfishCollector
from app.collectors.ipmi_collector import IPMIFleetCollector
from app.engines.health_score import HealthScoreEngine
from app.engines.alert_engine import AlertEngine, NotificationRouter
from app.services.credentials import CredentialProvider
from app.utils.family import derive_family, family_from_codename
from app.config import settings

log = structlog.get_logger(__name__)


async def _record_change(db, server, kind: str, new_value):
    """Insert a ChangeEvent only when (server, kind)'s value differs from the last recorded.
    First observation seeds silently (no row) to avoid a noisy initial entry."""
    from app.models.intelligence import ChangeEvent
    from sqlalchemy import select as _select
    if new_value is None:
        return
    new_value = str(new_value)
    last = (await db.execute(
        _select(ChangeEvent).where(ChangeEvent.server_id == server.id, ChangeEvent.kind == kind)
        .order_by(ChangeEvent.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if last is None:
        # seed baseline silently
        db.add(ChangeEvent(id=str(uuid.uuid4()), server_id=server.id, hostname=server.hostname,
                           kind=kind, old_value=None, new_value=new_value))
        return
    if last.new_value != new_value:
        db.add(ChangeEvent(id=str(uuid.uuid4()), server_id=server.id, hostname=server.hostname,
                           kind=kind, old_value=last.new_value, new_value=new_value))


async def _discover_os_ip_from_bmc(bmc_ip: str, bmc_port: int, username: str, password: str):
    """
    Query the BMC's Redfish for the HOST OS network IP (distinct from the BMC IP).
    Returns the first non-loopback IPv4 found on the host's EthernetInterfaces, else None.
    Many OpenBMC CRBs do not expose host NICs — caller falls back to fqdn/hostname.
    """
    import httpx
    base = f"https://{bmc_ip}:{bmc_port}"
    try:
        async with httpx.AsyncClient(verify=False, timeout=15,
                                     auth=(username, password)) as client:
            sysresp = await client.get(f"{base}/redfish/v1/Systems")
            members = sysresp.json().get("Members", [])
            if not members:
                return None
            system = (await client.get(f"{base}{members[0]['@odata.id']}")).json()
            eth_link = system.get("EthernetInterfaces", {}).get("@odata.id")
            if not eth_link:
                return None
            eth_coll = (await client.get(f"{base}{eth_link}")).json()
            for m in eth_coll.get("Members", []):
                nic = (await client.get(f"{base}{m['@odata.id']}")).json()
                for addr in nic.get("IPv4Addresses", []):
                    ip = addr.get("Address")
                    if ip and not ip.startswith("127.") and not ip.startswith("169.254"):
                        log.info("os_ip_discovered_from_bmc", bmc=bmc_ip, os_ip=ip)
                        return ip
    except Exception as e:
        log.debug("os_ip_discovery_failed", bmc=bmc_ip, error=str(e))
    return None


def _classify_util(cpu_pct, power_w, power_cap_w, power_state):
    """Derive a utilization bucket when PIPT hasn't provided one.

    Prefers OS CPU%; else uses power draw (absolute, or vs PSU capacity).
    Returns (bucket, score 0-9) or (None, None) if nothing usable.
    """
    if power_state and str(power_state).lower() in ("off", "poweringoff"):
        return "off", 0.0
    # CPU-based (most accurate, OS-agent servers)
    if cpu_pct is not None:
        if cpu_pct < 5:
            return "idle", 0.0
        if cpu_pct < 30:
            return "light", 3.0
        if cpu_pct < 70:
            return "active", 6.0
        return "heavy", 9.0
    # Power-based fallback (BMC-only servers): use ratio if capacity known
    if power_w and power_w > 0:
        if power_cap_w and power_cap_w > 0:
            r = power_w / power_cap_w
            if r < 0.15:
                return "idle", 0.0
            if r < 0.35:
                return "light", 3.0
            if r < 0.6:
                return "active", 6.0
            return "heavy", 9.0
        # No capacity: coarse absolute-watt heuristic for a 2-socket EPYC node
        if power_w < 150:
            return "idle", 0.0
        if power_w < 350:
            return "light", 3.0
        if power_w < 700:
            return "active", 6.0
        return "heavy", 9.0
    return None, None


def _snapshot_from_redfish(server_id: str, rf) -> MetricsSnapshot:
    """Build a MetricsSnapshot ORM object from RedfishMetrics."""
    cpu_temps = rf.cpu_temps or []
    fans_failed = sum(1 for f in rf.fans if f.get("failed"))
    psus_failed = sum(1 for p in rf.psus if not p.get("present", True) or
                      (p.get("status") and str(p.get("status")).lower() == "critical"))

    bucket, score = _classify_util(
        getattr(rf, "cpu_usage", None), rf.power_consumed_watts,
        rf.power_capacity_watts, rf.power_state,
    )

    return MetricsSnapshot(
        id=str(uuid.uuid4()),
        server_id=server_id,
        collected_at=rf.collected_at,
        cpu_temp_avg=round(sum(cpu_temps) / len(cpu_temps), 1) if cpu_temps else None,
        cpu_temp_max=max(cpu_temps) if cpu_temps else None,
        inlet_temp=rf.inlet_temp,
        outlet_temp=rf.outlet_temp,
        power_consumed_watts=rf.power_consumed_watts,
        power_capacity_watts=rf.power_capacity_watts,
        power_state=rf.power_state,
        fan_count=len(rf.fans),
        fan_failed_count=fans_failed,
        psu_count=len(rf.psus),
        psu_failed_count=psus_failed,
        sensor_health=rf.sensor_health,
        util_bucket=bucket,
        util_score=score,
        raw_sensors={
            "temperatures": rf.temperatures,
            "fans": rf.fans,
            "psus": rf.psus,
            "sel_events": rf.sel_events,
            "indicator_led": rf.indicator_led,
            "location_indicator_active": rf.location_indicator_active,
            "chassis_led": rf.chassis_led,
            "critical_sensors": rf.critical_sensors,
            "processors": getattr(rf, "processors", []),
        },
    )


async def _persist_components(db, server_id: str, rf) -> None:
    """Replace component inventory (DIMMs, disks, PSUs, NICs) for a server.

    DIMMs/PSUs are always refreshed from Redfish. Disks/NICs are only replaced
    when Redfish actually reports them — otherwise we keep richer PRISM-sourced
    inventory (CRB OpenBMC exposes no host disks/NICs over Redfish).
    """
    await db.execute(delete(DimmSlot).where(DimmSlot.server_id == server_id))
    await db.execute(delete(PSU).where(PSU.server_id == server_id))
    if rf.drives:
        await db.execute(delete(Disk).where(Disk.server_id == server_id))
    if rf.nics:
        await db.execute(delete(NIC).where(NIC.server_id == server_id))
    await db.flush()  # ensure deletes apply before re-inserts (unique constraints)

    for i, d in enumerate(rf.dimms or []):
        db.add(DimmSlot(
            id=str(uuid.uuid4()), server_id=server_id,
            slot_name=f"{d.get('name') or 'DIMM'}#{i}",
            capacity_gb=d.get("capacity_gb"),
            speed_mhz=d.get("speed_mhz"),
            manufacturer=d.get("manufacturer"),
            part_number=d.get("part_number"),
            serial_number=d.get("serial_number"),
            dimm_type=d.get("dimm_type"),
            health=d.get("status") or "OK",
            populated=bool(d.get("populated")),
        ))

    for d in (rf.drives or []):
        db.add(Disk(
            id=str(uuid.uuid4()), server_id=server_id,
            name=d.get("name"),
            model=d.get("model"),
            serial_number=d.get("serial_number"),
            capacity_gb=d.get("capacity_gb"),
            protocol=d.get("protocol"),
            media_type=d.get("media_type"),
            firmware_version=d.get("firmware_version"),
            health=d.get("status") or "OK",
            failure_predicted=bool(d.get("failure_predicted")),
            read_errors=d.get("read_errors") or 0,
            write_errors=d.get("write_errors") or 0,
        ))

    for i, p in enumerate(rf.psus or []):
        db.add(PSU(
            id=str(uuid.uuid4()), server_id=server_id,
            slot=f"{p.get('name') or 'PSU'}#{i}",
            model=p.get("model"),
            serial_number=p.get("serial_number"),
            capacity_watts=p.get("capacity_watts"),
            current_watts=p.get("current_watts"),
            voltage_v=p.get("voltage"),
            health=p.get("status") or "OK",
            present=bool(p.get("present", True)),
        ))

    for n in (rf.nics or []):
        ips = n.get("ip_addresses") or []
        speed = n.get("speed_mbps")
        # Keep a float Gbps so 100/1000 Mbps don't collapse to 0 (sub-Gb → 0.1, etc.).
        # speed_gbps column is widened to double precision via psql ALTER.
        db.add(NIC(
            id=str(uuid.uuid4()), server_id=server_id,
            name=n.get("name"),
            mac_address=n.get("mac_address"),
            speed_gbps=round(speed / 1000, 1) if speed else None,
            link_status=n.get("link_status"),
            ip_address=ips[0] if ips else None,
        ))


async def collect_redfish_all(only_server_id: str | None = None):
    """Collect Redfish metrics for all enabled servers (or a single server)."""
    async with AsyncSessionLocal() as db:
        q = select(Server).where(Server.redfish_enabled == True)  # noqa: E712
        if only_server_id:
            q = q.where(Server.id == only_server_id)
        result = await db.execute(q)
        servers = result.scalars().all()
        if not servers:
            return {"collected": 0, "reason": "no redfish-enabled servers"}

        provider = CredentialProvider()
        collector = FleetRedfishCollector(provider)
        metrics_list = await collector.collect_fleet(servers)

        collected = 0
        for server, rf in zip(servers, metrics_list):
            now = datetime.now(timezone.utc)
            if rf.error and not rf.partial_collection:
                server.status = ServerStatus.OFFLINE
                server.collection_error = rf.error
                server.last_collection_at = now
                continue

            snap = _snapshot_from_redfish(server.id, rf)
            db.add(snap)

            # Persist component inventory (DIMMs, disks, PSUs, NICs)
            await _persist_components(db, server.id, rf)

            # Update server identity if newly discovered
            if rf.model and not server.model:
                server.model = rf.model
            if rf.serial_number and not server.serial_number:
                server.serial_number = rf.serial_number
            if rf.bmc_firmware:
                server.bmc_firmware = rf.bmc_firmware
            if rf.bios_version:
                server.bios_version = rf.bios_version
            if rf.cpu_model and not server.cpu_model:
                server.cpu_model = rf.cpu_model
            if rf.cpu_count and not server.cpu_count:
                server.cpu_count = rf.cpu_count
            if getattr(rf, "cpu_cores_total", None):
                server.cpu_cores_total = rf.cpu_cores_total
            if getattr(rf, "cpu_threads_total", None):
                server.cpu_threads_total = rf.cpu_threads_total
            if getattr(rf, "microcode", None):
                server.microcode = rf.microcode
            # Family: real BMC model is authoritative — overwrite import-time guess.
            fam = derive_family(rf.cpu_model or rf.model)
            if fam:
                server.family = fam
            elif not server.family:
                server.family = family_from_codename(server.hostname)
            if rf.memory_gb and not server.memory_gb:
                server.memory_gb = rf.memory_gb
            if rf.dimms:
                server.dimm_count = sum(1 for d in rf.dimms if d.get("populated"))

            server.last_seen = now
            server.last_collection_at = now
            server.collection_error = None
            if server.status == ServerStatus.OFFLINE:
                server.status = ServerStatus.UNKNOWN
            collected += 1

        await db.commit()
        log.info("redfish_collection_done", total=len(servers), collected=collected)
        return {"collected": collected, "total": len(servers)}


async def collect_ipmi_all():
    """Collect IPMI metrics for servers where Redfish is unavailable."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Server).where(Server.ipmi_enabled == True, Server.redfish_enabled == False)  # noqa: E712
        )
        servers = result.scalars().all()
        if not servers:
            return {"collected": 0}

        provider = CredentialProvider()
        collector = IPMIFleetCollector(provider)
        collected = 0
        for server in servers:
            ipmi = await collector.collect_server(server)
            if ipmi.error:
                continue
            temps = [t["value"] for t in ipmi.temperatures if t.get("value")]
            snap = MetricsSnapshot(
                id=str(uuid.uuid4()),
                server_id=server.id,
                collected_at=ipmi.collected_at,
                cpu_temp_max=max(temps) if temps else None,
                cpu_temp_avg=round(sum(temps) / len(temps), 1) if temps else None,
                raw_sensors={
                    "temperatures": ipmi.temperatures,
                    "voltages": ipmi.voltages,
                    "fans": ipmi.fans,
                    "sel_events": ipmi.sel_events,
                    "chassis_status": ipmi.chassis_status,
                },
            )
            db.add(snap)
            server.last_seen = datetime.now(timezone.utc)
            collected += 1
        await db.commit()
        return {"collected": collected}


async def enrich_from_prism(only_hostname: str | None = None):
    """Enrich servers with hardware + OS IP from the PRISM OS-Provisioning API."""
    from app.collectors.prism_client import PrismClient, extract_os_ip, extract_hardware

    client = PrismClient()
    enriched, not_found, errors = 0, 0, 0
    async with AsyncSessionLocal() as db:
        q = select(Server)
        if only_hostname:
            q = q.where(Server.hostname == only_hostname)
        servers = (await db.execute(q)).scalars().all()

        for server in servers:
            try:
                tree = await client.hardware_info(server.hostname)
            except Exception as e:
                errors += 1
                log.warning("prism_enrich_error", host=server.hostname, error=str(e))
                continue
            if not tree:
                not_found += 1
                continue

            os_ip = extract_os_ip(tree)
            hw = extract_hardware(tree)

            if os_ip:
                server.os_ip = os_ip
                server.os_agent_enabled = True  # SSH activates once valid OS creds exist
            if hw.get("cpu_model"):
                server.cpu_model = hw["cpu_model"]
            if hw.get("cpu_count"):
                server.cpu_count = hw["cpu_count"]
            if hw.get("memory_gb"):
                server.memory_gb = hw["memory_gb"]
            if hw.get("dimm_count"):
                server.dimm_count = hw["dimm_count"]

            # Replace disks + NICs from PRISM (delete-then-insert, like _persist_components)
            await db.execute(delete(Disk).where(Disk.server_id == server.id))
            await db.execute(delete(NIC).where(NIC.server_id == server.id))
            await db.flush()
            for i, d in enumerate(hw.get("disks", [])):
                db.add(Disk(
                    id=str(uuid.uuid4()), server_id=server.id,
                    name=d.get("name") or f"disk{i}", model=d.get("model"),
                    serial_number=d.get("serial_number"), capacity_gb=d.get("capacity_gb"),
                    media_type=d.get("media_type"), protocol=d.get("media_type"), health="OK",
                ))
            for i, n in enumerate(hw.get("nics", [])):
                mac = n.get("mac_address")
                if mac and len(mac) > 17:
                    mac = mac[:17]
                db.add(NIC(
                    id=str(uuid.uuid4()), server_id=server.id,
                    name=(n.get("name") or f"nic{i}")[:64], driver=n.get("model"),
                    mac_address=mac, speed_gbps=n.get("speed_gbps"),
                    link_status=n.get("link_status"),
                ))
            # Commit per server so locks release immediately between hosts — avoids
            # deadlocking against the 60s Redfish collect over a long fleet run.
            try:
                await db.commit()
                enriched += 1
            except Exception as e:
                await db.rollback()
                errors += 1
                log.warning("prism_enrich_commit_failed", host=server.hostname, error=str(e))

    log.info("prism_enrich_done", enriched=enriched, not_found=not_found, errors=errors)
    return {"enriched": enriched, "not_found": not_found, "errors": errors}


async def _collect_os_targets(targets):
    """Collect OS metrics for [(server, host, creds), ...] concurrently with per-server creds.

    Returns a list of OSMetrics (order matches targets). Shares one semaphore so
    unreachable subnets fast-fail without exceeding the configured concurrency.
    """
    import asyncio as _asyncio
    from app.collectors.os_agent import OSAgentCollector, OSMetrics

    sem = _asyncio.Semaphore(settings.OS_AGENT_CONCURRENT_LIMIT)

    async def _one(server, host, creds):
        async with sem:
            agent = OSAgentCollector(
                server.id, host, creds["username"], creds["password"],
                timeout=settings.OS_AGENT_CONNECT_TIMEOUT,
                port_check_timeout=settings.OS_AGENT_PORT_CHECK_TIMEOUT,
            )
            return await agent.collect()

    results = await _asyncio.gather(
        *[_one(s, h, c) for s, h, c in targets], return_exceptions=True
    )
    out = []
    for (s, _, _), r in zip(targets, results):
        if isinstance(r, OSMetrics):
            out.append(r)
        else:
            m = OSMetrics(s.id)
            m.error = str(r) if r else "collect failed"
            out.append(m)
    return out


async def collect_os_all(only_server_id: str | None = None):
    """Collect OS CPU/memory over SSH for os_agent_enabled servers — CONCURRENTLY.

    Uses OSAgentFleetCollector (semaphore-bounded asyncio.gather) with a fast TCP
    pre-check so unreachable subnets drop in ~2s. A full cycle finishes within the
    30s schedule even when most OS IPs are unroutable.
    """
    from app.collectors.os_agent import OSAgentFleetCollector
    from app.services.credentials import OSCredentialProvider
    from app.models.users import UserSession

    async with AsyncSessionLocal() as db:
        q = select(Server).where(Server.os_agent_enabled == True)  # noqa: E712
        if only_server_id:
            q = q.where(Server.id == only_server_id)
        result = await db.execute(q)
        servers = result.scalars().all()
        if not servers:
            return {"collected": 0, "reason": "no os_agent-enabled servers"}

        provider = OSCredentialProvider()
        # Per-server creds (os_username/os_password on the row) take priority; falls
        # back to DEFAULT_OS_* env. Servers may carry different creds, so collect each
        # host with its own credential under a shared concurrency semaphore.
        targets = []  # (server, host, creds)
        for server in servers:
            creds = await provider.get_credentials(server.id, server=server)
            if not creds:
                continue
            host = server.os_ip or server.fqdn or server.hostname
            if not host:
                continue
            targets.append((server, host, creds))

        if not targets:
            return {"collected": 0, "reason": "no resolvable OS hosts"}

        metrics_list = await _collect_os_targets(targets)

        by_server = {s.id: s for s, _, _ in targets}
        now = datetime.now(timezone.utc)
        collected = 0
        unreachable = 0
        for m in metrics_list:
            server = by_server.get(m.server_id)
            if server is None:
                continue
            if m.error:
                if "unreachable" in (m.error or ""):
                    unreachable += 1
                continue

            # Merge OS fields into the latest snapshot (or create one)
            snap_res = await db.execute(
                select(MetricsSnapshot).where(MetricsSnapshot.server_id == server.id)
                .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
            )
            snap = snap_res.scalar_one_or_none()
            if snap is None or (now - snap.collected_at).total_seconds() > 120:
                snap = MetricsSnapshot(id=str(uuid.uuid4()), server_id=server.id,
                                       collected_at=now)
                db.add(snap)
            snap.cpu_usage_avg = m.cpu_usage_pct
            snap.cpu_usage_max = m.cpu_usage_pct
            snap.load_avg_1m = m.load_1m
            snap.load_avg_5m = m.load_5m
            snap.load_avg_15m = m.load_15m
            snap.memory_usage_pct = m.memory_usage_pct
            snap.memory_used_gb = m.memory_used_gb
            snap.memory_free_gb = m.memory_free_gb
            snap.swap_usage_pct = m.swap_usage_pct
            snap.disk_usage_avg_pct = m.disk_usage_avg_pct
            snap.disk_usage_max_pct = m.disk_usage_max_pct
            snap.net_rx_mbps = m.net_rx_mbps
            snap.net_tx_mbps = m.net_tx_mbps

            # Reconcile active sessions: mark all inactive, re-add current
            await db.execute(
                UserSession.__table__.update()
                .where(UserSession.server_id == server.id, UserSession.is_active == True)  # noqa: E712
                .values(is_active=False)
            )
            for sess in m.sessions:
                db.add(UserSession(
                    id=str(uuid.uuid4()), server_id=server.id,
                    username=sess["username"], session_type=sess.get("session_type"),
                    source_ip=sess.get("source_ip"), terminal=sess.get("terminal"),
                    login_at=m.collected_at, is_active=True,
                ))
            collected += 1

        await db.commit()
        log.info("os_collection_done", enabled=len(servers), attempted=len(targets),
                 collected=collected, unreachable=unreachable)
        return {"enabled": len(servers), "attempted": len(targets),
                "collected": collected, "unreachable": unreachable}


async def full_refresh_server(server_id: str):
    """On-demand full enrichment for one server: Redfish → PRISM → OS agent.

    Used right after a server is added (Settings) or its OS IP edited (Network),
    so it populates immediately without waiting for the next scheduled cycle.
    """
    result = {"server_id": server_id}
    # Resolve hostname for PRISM (needs hostname, not id)
    async with AsyncSessionLocal() as db:
        server = (await db.execute(select(Server).where(Server.id == server_id))).scalar_one_or_none()
        hostname = server.hostname if server else None
        redfish_enabled = bool(server and server.redfish_enabled)
        os_enabled = bool(server and server.os_agent_enabled)

    if redfish_enabled:
        try:
            result["redfish"] = await collect_redfish_all(only_server_id=server_id)
        except Exception as e:
            result["redfish_error"] = str(e)
    if hostname:
        try:
            result["prism"] = await enrich_from_prism(only_hostname=hostname)
        except Exception as e:
            result["prism_error"] = str(e)
    if os_enabled:
        try:
            result["os"] = await collect_os_all(only_server_id=server_id)
        except Exception as e:
            result["os_error"] = str(e)
    # Recompute health for the fresh data
    try:
        await compute_all_health_scores()
    except Exception as e:
        result["health_error"] = str(e)
    return result


async def collect_pipt_all():
    """Pull PIPT /fleet BMC telemetry and merge into the latest snapshot per host.

    Fills temp/power/fan/SEL where Redfish didn't provide them (e.g. unreachable
    or Milan servers), and refreshes last_seen so PIPT-tracked hosts stay live.
    """
    from app.collectors.pipt_client import PiptClient, normalize_host

    hosts = await PiptClient().fleet()
    if not hosts:
        return {"merged": 0, "reason": "no pipt data"}

    by_host = {normalize_host(h.get("host")): h for h in hosts if h.get("host")}
    now = datetime.now(timezone.utc)
    merged = 0
    async with AsyncSessionLocal() as db:
        servers = (await db.execute(select(Server))).scalars().all()
        for server in servers:
            p = by_host.get(server.hostname.lower())
            if not p:
                continue

            snap_res = await db.execute(
                select(MetricsSnapshot).where(MetricsSnapshot.server_id == server.id)
                .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
            )
            snap = snap_res.scalar_one_or_none()
            # Only create/merge into a recent snapshot; else make a fresh one
            if snap is None or (now - snap.collected_at).total_seconds() > 300:
                snap = MetricsSnapshot(id=str(uuid.uuid4()), server_id=server.id, collected_at=now)
                db.add(snap)

            # Fill fields where missing (Redfish wins if already set this cycle)
            if p.get("watts") is not None and snap.power_consumed_watts is None:
                snap.power_consumed_watts = float(p["watts"])
            if p.get("hottest_c") is not None and snap.cpu_temp_max is None:
                snap.cpu_temp_max = float(p["hottest_c"])
                snap.cpu_temp_avg = snap.cpu_temp_avg or float(p["hottest_c"])
            if p.get("fan_rpm_max") is not None and snap.fan_speed_avg_rpm is None:
                snap.fan_speed_avg_rpm = int(p["fan_rpm_max"])
            if p.get("power_state") and snap.power_state is None:
                snap.power_state = p["power_state"]
            # Persist utilization bucket + numeric score for fast aggregation
            bucket = p.get("bucket")
            if bucket:
                snap.util_bucket = bucket
                snap.util_score = {"idle": 0.0, "light": 3.0, "active": 6.0, "heavy": 9.0}.get(bucket)

            # Always stash PIPT extras in raw_sensors (incl. drift)
            raw = snap.raw_sensors or {}
            raw["pipt"] = {
                "cpu_watts": p.get("cpu_watts"), "total_sel": p.get("total_sel"),
                "new_critical_sel": p.get("new_critical_sel"), "bucket": p.get("bucket"),
                "status": p.get("status"), "drift": p.get("drift"), "ts": p.get("ts"),
            }
            snap.raw_sensors = raw

            # Changelog: power + drift transitions
            if p.get("power_state"):
                await _record_change(db, server, "power", p["power_state"])
            if p.get("drift") is not None:
                await _record_change(db, server, "drift", "YES" if p["drift"] else "no")

            server.last_seen = now
            if server.status == ServerStatus.OFFLINE and p.get("power_state") == "On":
                server.status = ServerStatus.UNKNOWN  # will be re-scored by health task
            merged += 1

        await db.commit()
    log.info("pipt_merge_done", merged=merged)
    return {"merged": merged, "pipt_hosts": len(by_host)}


async def compute_all_health_scores():
    """Recompute health scores from each server's latest snapshot.

    Staleness gate: a server that has not reported within STALE_SECONDS (or never)
    is marked OFFLINE with score 0 — "no data" must never read as healthy.
    """
    STALE_SECONDS = 1200  # 20 min without a fresh snapshot => offline. Wider than the
    # 300s Redfish interval + worst-case ~7min cycle so a single slow poll cycle
    # doesn't flip reachable servers to OFFLINE (avoids the offline/unknown flicker).
    now = datetime.now(timezone.utc)
    HEARTBEAT_SECONDS = 3600  # write a history row at least hourly even if unchanged
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Server))
        servers = result.scalars().all()
        engine = HealthScoreEngine()
        scored = 0

        # Latest health-history row per server (one query, not N) so we can skip
        # writing a new row when nothing changed — the big write-volume reducer.
        last_hs = {h.server_id: h for h in (await db.execute(
            select(HealthScore).distinct(HealthScore.server_id)
            .order_by(HealthScore.server_id, HealthScore.scored_at.desc())
        )).scalars().all()}

        def _should_write(server_id: str, score, status) -> bool:
            prev = last_hs.get(server_id)
            if prev is None:
                return True
            # Status change, or score moved by >=1 point → always record.
            if (prev.status or "") != (status or ""):
                return True
            try:
                if abs((prev.total_score or 0) - (score or 0)) >= 1.0:
                    return True
            except TypeError:
                return True
            # Otherwise only a periodic heartbeat keeps the trend line continuous.
            if prev.scored_at and (now - prev.scored_at).total_seconds() >= HEARTBEAT_SECONDS:
                return True
            return False

        for server in servers:
            # Collectors can emit a mix of full Redfish snapshots and empty/partial ones
            # (e.g. a PIPT-only row with no thermal). Blindly taking the latest row can
            # land on an empty one and falsely mark the server UNKNOWN. So scan the recent
            # snapshots and prefer the newest that actually carries telemetry.
            recent = (await db.execute(
                select(MetricsSnapshot)
                .where(MetricsSnapshot.server_id == server.id)
                .order_by(MetricsSnapshot.collected_at.desc())
                .limit(8)
            )).scalars().all()
            snapshot = recent[0] if recent else None
            _TFIELDS = ("cpu_temp_max", "cpu_temp_avg", "inlet_temp", "power_consumed_watts",
                        "fan_count", "psu_count", "cpu_usage_avg", "memory_usage_pct")
            for r in recent:
                if any(getattr(r, f, None) not in (None, 0) for f in _TFIELDS) or getattr(r, "sensor_health", None):
                    snapshot = r
                    break

            # Determine staleness from the freshest of last_seen / latest snapshot time
            latest_ts = recent[0].collected_at if recent else None
            last = server.last_seen
            if latest_ts and (last is None or latest_ts > last):
                last = latest_ts
            is_stale = last is None or (now - last).total_seconds() > STALE_SECONDS

            if is_stale:
                # No recent data => OFFLINE, score 0, explicit deduction. Do NOT score as healthy.
                reason = "Never collected" if last is None else f"No data for {int((now - last).total_seconds() // 60)} min"
                if _should_write(server.id, 0.0, "offline"):
                    db.add(HealthScore(
                        id=str(uuid.uuid4()), server_id=server.id,
                        total_score=0.0, status="offline",
                        hardware_score=0, thermal_score=0, power_score=0,
                        storage_score=0, network_score=0, utilization_score=0,
                        hardware_contribution=0, thermal_contribution=0, power_contribution=0,
                        storage_contribution=0, network_contribution=0, utilization_contribution=0,
                        deductions=[{"component": "availability", "reason": reason, "points": -100, "severity": "critical"}],
                    ))
                server.health_score = 0.0
                server.status = ServerStatus.OFFLINE
                scored += 1
                continue

            # "No telemetry" gate: a fresh snapshot that carries NO usable sensor
            # data (no temp/power/fans/psus/cpu/mem) must not read as green Healthy —
            # absence of evidence is not health. Mark UNKNOWN with a neutral score.
            _has_telemetry = any(getattr(snapshot, f, None) not in (None, 0) for f in (
                "cpu_temp_max", "cpu_temp_avg", "inlet_temp", "power_consumed_watts",
                "fan_count", "psu_count", "cpu_usage_avg", "memory_usage_pct",
            ))
            if not _has_telemetry and getattr(snapshot, "sensor_health", None) is None:
                if _should_write(server.id, 0.0, "unknown"):
                    db.add(HealthScore(
                        id=str(uuid.uuid4()), server_id=server.id,
                        total_score=0.0, status="unknown",
                        hardware_score=0, thermal_score=0, power_score=0,
                        storage_score=0, network_score=0, utilization_score=0,
                        hardware_contribution=0, thermal_contribution=0, power_contribution=0,
                        storage_contribution=0, network_contribution=0, utilization_contribution=0,
                        deductions=[{"component": "availability",
                                     "reason": "BMC reachable but reported no sensor data",
                                     "points": 0, "severity": "warning"}],
                    ))
                server.health_score = None
                if server.status != ServerStatus.UNKNOWN:
                    await _record_change(db, server, "status", "unknown")
                server.status = ServerStatus.UNKNOWN
                scored += 1
                continue

            res = engine.calculate(snapshot, server)
            server.health_score = res.total_score
            # Fresh data present → reflect computed status (also recovers from prior OFFLINE)
            new_status = ServerStatus(res.status)
            rank = {"healthy": 0, "warning": 1, "at_risk": 2, "critical": 3}
            # Floor 1: a BMC-declared Critical/Warning sensor must not read as healthy,
            # even if the weighted score stays high (single hardware fault = real).
            sh = getattr(snapshot, "sensor_health", None)
            if sh == "Critical" and rank.get(new_status.value, 0) < rank["critical"]:
                new_status = ServerStatus.CRITICAL
            elif sh == "Warning" and rank.get(new_status.value, 0) < rank["warning"]:
                new_status = ServerStatus.WARNING
            # Floor 2: a Critical SEL (System Event Log) entry also floors to critical,
            # and a Warning SEL to at least warning — so the dashboard's critical count
            # reflects SEL events, not just live thermal sensors.
            raw = getattr(snapshot, "raw_sensors", None) or {}
            sel = raw.get("sel_events") or []
            sel_sevs = {str(e.get("severity", "")).lower() for e in sel if isinstance(e, dict)}
            if "critical" in sel_sevs and rank.get(new_status.value, 0) < rank["critical"]:
                new_status = ServerStatus.CRITICAL
            elif "warning" in sel_sevs and rank.get(new_status.value, 0) < rank["warning"]:
                new_status = ServerStatus.WARNING
            # Persist a history row only on change or hourly heartbeat (write-volume cut)
            if _should_write(server.id, res.total_score, new_status.value):
                db.add(HealthScore(
                    id=str(uuid.uuid4()), server_id=server.id,
                    total_score=res.total_score, status=new_status.value,
                    hardware_score=res.hardware_score, thermal_score=res.thermal_score,
                    power_score=res.power_score, storage_score=res.storage_score,
                    network_score=res.network_score, utilization_score=res.utilization_score,
                    hardware_contribution=res.hardware_contribution,
                    thermal_contribution=res.thermal_contribution,
                    power_contribution=res.power_contribution,
                    storage_contribution=res.storage_contribution,
                    network_contribution=res.network_contribution,
                    utilization_contribution=res.utilization_contribution,
                    deductions=res.deductions_as_dicts,
                ))
            await _record_change(db, server, "status", new_status.value)
            server.status = new_status
            scored += 1

        await db.commit()
        log.info("health_scores_computed", scored=scored)
        return {"scored": scored}


async def backfill_status_changes(hours: int = 48):
    """One-shot: derive STATUS ChangeEvents from health_scores history so the
    changelog isn't empty on first deploy. Walks each server's scored rows in order."""
    from app.models.intelligence import ChangeEvent
    cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=hours)
    inserted = 0
    async with AsyncSessionLocal() as db:
        servers = (await db.execute(select(Server))).scalars().all()
        host_by_id = {s.id: s.hostname for s in servers}
        rows = (await db.execute(
            select(HealthScore.server_id, HealthScore.status, HealthScore.scored_at)
            .where(HealthScore.scored_at >= cutoff)
            .order_by(HealthScore.server_id, HealthScore.scored_at.asc())
        )).all()
        last_status = {}
        for sid, status, ts in rows:
            prev = last_status.get(sid)
            if prev is not None and prev != status:
                db.add(ChangeEvent(id=str(uuid.uuid4()), server_id=sid,
                                   hostname=host_by_id.get(sid, "—"), kind="status",
                                   old_value=prev, new_value=status, created_at=ts))
                inserted += 1
            last_status[sid] = status
        await db.commit()
    log.info("backfill_status_done", inserted=inserted)
    return {"inserted": inserted}


async def prune_change_events(days: int = 7):
    """Bound changelog growth — delete events older than N days."""
    from app.models.intelligence import ChangeEvent
    cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ChangeEvent).where(ChangeEvent.created_at < cutoff))
        await db.commit()
    return {"pruned_before": cutoff.isoformat()}


async def prune_snapshots():
    """Retention: delete raw metrics_snapshots older than SNAPSHOT_RETENTION_HOURS.
    Trends live in health_scores; raw snapshots only need a short window. This is the
    key control that keeps the dashboard fast as the fleet runs continuously."""
    from app.models.intelligence import RiskScore
    hours = settings.SNAPSHOT_RETENTION_HOURS
    cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(MetricsSnapshot).where(MetricsSnapshot.collected_at < cutoff))
        # Bound history tables. health_scores now writes on-change so it stays small;
        # risk_scores is rewritten every cycle, so it MUST be pruned (was leaking before).
        # The trend chart only shows ~48h, so keep 3 days of health history.
        hs_cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=3)
        risk_cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=2)
        await db.execute(delete(HealthScore).where(HealthScore.scored_at < hs_cutoff))
        await db.execute(delete(RiskScore).where(RiskScore.scored_at < risk_cutoff))
        await db.commit()
    log.info("prune_snapshots_done", retention_hours=hours)
    return {"pruned_snapshots_before": cutoff.isoformat()}


async def compute_risk_and_recommendations():
    """Run predictive + optimization + firmware + recommendation engines; persist results."""
    from app.models.intelligence import RiskScore, Recommendation
    from app.models.users import UserSession
    from app.engines.predictive import PredictiveMaintenanceEngine
    from app.engines.optimization import ResourceOptimizer
    from app.engines.firmware import FirmwareCompliance
    from app.engines.recommendations import RecommendationEngine

    async with AsyncSessionLocal() as db:
        servers = (await db.execute(select(Server))).scalars().all()
        pred = PredictiveMaintenanceEngine()
        opt = ResourceOptimizer()
        fw = FirmwareCompliance()
        reco_engine = RecommendationEngine()

        # active-user servers
        sess = (await db.execute(select(UserSession).where(UserSession.is_active == True))).scalars().all()  # noqa: E712
        active_user_servers = {s.server_id for s in sess}

        # Clear old (non-dismissed) recommendations so the feed reflects current state
        await db.execute(delete(Recommendation).where(Recommendation.dismissed == False))  # noqa: E712
        await db.flush()

        scored = 0
        recos_made = 0
        for server in servers:
            snap = (await db.execute(
                select(MetricsSnapshot).where(MetricsSnapshot.server_id == server.id)
                .order_by(MetricsSnapshot.collected_at.desc()).limit(1)
            )).scalar_one_or_none()
            disks = (await db.execute(select(Disk).where(Disk.server_id == server.id))).scalars().all()
            dimms = (await db.execute(select(DimmSlot).where(DimmSlot.server_id == server.id))).scalars().all()

            risk = pred.calculate(server, snap, disks, dimms)
            db.add(RiskScore(
                id=str(uuid.uuid4()), server_id=server.id,
                overall_risk=risk.overall_risk, risk_level=risk.risk_level,
                disk_risk=risk.disk_risk, psu_risk=risk.psu_risk, fan_risk=risk.fan_risk,
                memory_risk=risk.memory_risk, thermal_risk=risk.thermal_risk, factors=risk.factors,
            ))
            scored += 1

            util = opt.classify(snap, server.id in active_user_servers)
            fw_res = fw.evaluate(server)

            for r in reco_engine.generate(server, snap, risk, util, fw_res):
                db.add(Recommendation(
                    id=str(uuid.uuid4()), server_id=server.id,
                    category=r.category, severity=r.severity, title=r.title,
                    body=r.body, rationale=r.rationale, steps=r.steps,
                ))
                recos_made += 1

        await db.commit()
        log.info("risk_recos_computed", scored=scored, recos=recos_made)
    # Bound changelog growth (runs on the 5-min risk cadence)
    try:
        await prune_change_events(days=7)
    except Exception as e:
        log.debug("prune_change_events_failed", error=str(e))
    return {"scored": scored, "recommendations": recos_made}


async def evaluate_all_alerts():
    """Evaluate alert rules and fire/notify on new alerts."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Server))
        servers = result.scalars().all()
        engine = AlertEngine()
        router = NotificationRouter()
        fired = 0
        resolved = 0

        for server in servers:
            snap_res = await db.execute(
                select(MetricsSnapshot)
                .where(MetricsSnapshot.server_id == server.id)
                .order_by(MetricsSnapshot.collected_at.desc())
                .limit(1)
            )
            snapshot = snap_res.scalar_one_or_none()

            active_res = await db.execute(
                select(Alert).where(Alert.server_id == server.id, Alert.state == AlertState.FIRING)
            )
            active = active_res.scalars().all()
            active_names = {a.title for a in active}

            # Auto-resolve: any firing alert whose condition no longer holds.
            still_firing = engine.active_rule_titles(server, snapshot)
            for a in active:
                if a.title not in still_firing:
                    a.state = AlertState.RESOLVED
                    a.resolved_at = datetime.now(timezone.utc)
                    resolved += 1

            new_alerts = engine.evaluate(server, snapshot, active_names)
            for alert_data in new_alerts:
                alert = Alert(**{k: v for k, v in alert_data.items() if hasattr(Alert, k)})
                db.add(alert)
                fired += 1
                try:
                    await router.notify(alert_data, server)
                except Exception as e:
                    log.warning("notify_failed", error=str(e))

        await db.commit()
        log.info("alerts_evaluated", fired=fired, resolved=resolved)
        return {"fired": fired, "resolved": resolved}


# ---------------------------------------------------------------------------
# Autonomous SEL triage (Tier-2: reversible actions only).
# Scans latest SEL events, asks the AI to classify each NEW one, and either
# logs the verdict (shadow mode) or takes a REVERSIBLE action (ack noise /
# raise an alert). Never reboots or flashes — those stay human-approved.
# ---------------------------------------------------------------------------

_TRIAGE_SYS = (
    "You are an SRE triaging BMC System Event Log (SEL) entries for AMD EPYC servers. "
    "For each event decide:\n"
    "  verdict: 'noise' (benign/informational/expected — e.g. routine power-on, sensor "
    "re-arm, log cleared), 'hardware_issue' (real fault needing attention — e.g. "
    "uncorrectable ECC, PSU failure, fan fault, thermal trip, CPU/DIMM error), or "
    "'needs_review' (ambiguous / not enough context).\n"
    "  confidence: 0.0-1.0\n"
    "  reasoning: one short sentence.\n"
    "Be conservative: if a real fault is plausible, prefer 'hardware_issue' or "
    "'needs_review' over 'noise'. Reply ONLY with a JSON array, one object per event, "
    "in the same order, each: {\"verdict\":..., \"confidence\":..., \"reasoning\":...}."
)

_SEL_SEV_TO_ALERT = {
    "critical": "critical",
    "warning": "warning",
}


def _sel_event_key(hostname: str, ev: dict) -> str:
    """Stable dedup key for a SEL event."""
    return f"{hostname}|{ev.get('id') or ev.get('message','')[:60]}|{ev.get('timestamp') or ev.get('created') or ''}"


async def autonomous_sel_triage():
    """Periodic Tier-2 autonomous loop. Honors the global kill switch + shadow mode."""
    if not settings.SEL_AUTOTRIAGE_ENABLED:
        return {"status": "disabled"}
    if settings.AUTONOMY_PAUSED:
        log.info("sel_triage_skipped", reason="autonomy_paused")
        return {"status": "autonomy_paused"}

    from app.models.intelligence import TriageLog
    from app.models.alerts import AlertSeverity, AlertCategory
    from app.ai.client import llm, LLMUnavailable

    if not llm.enabled:
        return {"status": "llm_unavailable"}

    shadow = settings.SEL_AUTOTRIAGE_SHADOW
    async with AsyncSessionLocal() as db:
        servers = {s.id: s for s in (await db.execute(select(Server))).scalars().all()}
        # Latest snapshot per server, newest first
        snaps = (await db.execute(
            select(MetricsSnapshot).distinct(MetricsSnapshot.server_id)
            .order_by(MetricsSnapshot.server_id, MetricsSnapshot.collected_at.desc())
        )).scalars().all()

        # Gather NEW, non-info SEL events not already in triage_logs
        candidates = []  # (server, event, key)
        for snap in snaps:
            srv = servers.get(snap.server_id)
            if not srv:
                continue
            for ev in (snap.raw_sensors or {}).get("sel_events", []) or []:
                if not isinstance(ev, dict):
                    continue
                sev = str(ev.get("severity") or "Info").lower()
                if sev not in ("critical", "warning"):
                    continue
                key = _sel_event_key(srv.hostname, ev)
                candidates.append((srv, ev, key))

        if not candidates:
            return {"status": "ok", "new_events": 0}

        keys = [k for _, _, k in candidates]
        existing = set((await db.execute(
            select(TriageLog.event_key).where(TriageLog.event_key.in_(keys))
        )).scalars().all())
        fresh = [(srv, ev, k) for srv, ev, k in candidates if k not in existing][:40]
        if not fresh:
            return {"status": "ok", "new_events": 0}

        # Ask the AI to classify all fresh events in one call
        listing = "\n".join(
            f"{i+1}. host={srv.hostname} sev={ev.get('severity')} msg={ev.get('message','')[:200]}"
            for i, (srv, ev, _) in enumerate(fresh)
        )
        try:
            msg = await llm.chat(
                [{"role": "system", "content": _TRIAGE_SYS},
                 {"role": "user", "content": f"Triage these {len(fresh)} SEL events:\n{listing}"}],
                temperature=0.0, max_tokens=2000,
            )
            verdicts = _parse_json_array(msg.get("content") or "")
        except LLMUnavailable as e:
            log.warning("sel_triage_llm_failed", error=str(e))
            return {"status": "llm_unavailable"}

        acted = 0
        logged = 0
        for i, (srv, ev, key) in enumerate(fresh):
            v = verdicts[i] if i < len(verdicts) else {}
            verdict = str(v.get("verdict") or "needs_review").lower()
            if verdict not in ("noise", "hardware_issue", "needs_review"):
                verdict = "needs_review"
            conf = float(v.get("confidence") or 0.0)
            reasoning = str(v.get("reasoning") or "")[:2000]
            sev = str(ev.get("severity") or "Info")

            action = "shadow" if shadow else "none"
            alert_id = None

            if not shadow:
                if verdict == "hardware_issue":
                    sev_key = sev.lower()
                    a_sev = AlertSeverity(_SEL_SEV_TO_ALERT.get(sev_key, "warning"))
                    alert = Alert(
                        id=str(uuid.uuid4()), server_id=srv.id,
                        severity=a_sev, category=AlertCategory.HARDWARE,
                        state=AlertState.FIRING,
                        title=f"SEL hardware event: {ev.get('message','')[:120]}",
                        message=f"Autonomous SEL triage flagged a hardware issue "
                                f"(confidence {conf:.0%}): {reasoning}",
                        details={"sel_event": ev, "verdict": verdict, "confidence": conf,
                                 "source": "autonomous_sel_triage"},
                    )
                    db.add(alert)
                    alert_id = alert.id
                    action = "alert_created"
                    acted += 1
                elif verdict == "noise" and conf >= 0.8:
                    # Reversible: just record that we auto-dismissed it as noise.
                    action = "acknowledged"
                    acted += 1

            db.add(TriageLog(
                id=str(uuid.uuid4()), event_key=key, server_id=srv.id, hostname=srv.hostname,
                severity=sev, message=str(ev.get("message", ""))[:1024],
                verdict=verdict, confidence=conf, reasoning=reasoning,
                action_taken=action, shadow=shadow, alert_id=alert_id,
            ))
            logged += 1

        await db.commit()
        log.info("sel_triage_done", new_events=len(fresh), logged=logged,
                 acted=acted, shadow=shadow)
        return {"status": "ok", "new_events": len(fresh), "logged": logged,
                "acted": acted, "shadow": shadow}


def _parse_json_array(text: str) -> list:
    """Best-effort parse of a JSON array from an LLM response (tolerates code fences/prose)."""
    import json, re
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", t).strip()
    try:
        v = json.loads(t)
        return v if isinstance(v, list) else []
    except Exception:
        m = re.search(r"\[.*\]", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return []
        return []
