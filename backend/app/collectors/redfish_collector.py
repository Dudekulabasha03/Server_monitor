"""
Redfish API Collector — async, multi-vendor, production-grade.

Supports: Dell iDRAC, HPE iLO, Lenovo XCC, Supermicro BMC, AMD CRB BMC
"""
import asyncio
import ssl
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import settings

log = structlog.get_logger(__name__)


def _canon_link(raw) -> Optional[str]:
    """Normalize any BMC link-state string to canonical 'Up' / 'Down'.
    Returns None only when nothing was reported (so callers can leave it blank)."""
    if not raw:
        return None
    s = "".join(c for c in str(raw).lower() if c.isalpha())
    if s in ("up", "linkup", "enabled", "connected", "active"):
        return "Up"
    return "Down"


class RedfishVendor:
    DELL = "dell"
    HPE = "hpe"
    LENOVO = "lenovo"
    SUPERMICRO = "supermicro"
    AMD = "amd"
    GENERIC = "generic"


class RedfishMetrics:
    """Normalized output from any Redfish collection."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self.collected_at = datetime.now(timezone.utc)
        self.vendor: Optional[str] = None
        self.model: Optional[str] = None
        self.serial_number: Optional[str] = None
        self.bios_version: Optional[str] = None
        self.bmc_firmware: Optional[str] = None

        # Power
        self.power_consumed_watts: Optional[float] = None
        self.power_capacity_watts: Optional[float] = None
        self.power_state: Optional[str] = None
        self.psus: List[Dict[str, Any]] = []

        # Thermal
        self.temperatures: List[Dict[str, Any]] = []  # [{name, reading, upper_threshold_critical}]
        self.fans: List[Dict[str, Any]] = []           # [{name, rpm, status}]
        self.inlet_temp: Optional[float] = None
        self.outlet_temp: Optional[float] = None
        self.cpu_temps: List[float] = []

        # CPU
        self.cpu_count: Optional[int] = None
        self.cpu_model: Optional[str] = None
        self.cpu_usage: Optional[float] = None  # % - if available
        self.cpu_cores_total: Optional[int] = None
        self.cpu_threads_total: Optional[int] = None
        self.microcode: Optional[str] = None  # primary-CPU microcode revision
        self.processors: List[Dict[str, Any]] = []  # [{id, model, cores, threads, microcode, health}]

        # Memory
        self.memory_gb: Optional[int] = None
        self.memory_usage: Optional[float] = None
        self.dimms: List[Dict[str, Any]] = []

        # Storage
        self.drives: List[Dict[str, Any]] = []
        self.volumes: List[Dict[str, Any]] = []

        # Network
        self.nics: List[Dict[str, Any]] = []

        # Events (last 20 from SEL)
        self.sel_events: List[Dict[str, Any]] = []

        # Indicator LEDs
        self.indicator_led: Optional[str] = None
        self.location_indicator_active: Optional[bool] = None
        self.chassis_led: Optional[str] = None

        # BMC-declared sensor health (worst across temps/fans/PSUs) + offending sensors
        self.sensor_health: Optional[str] = None  # OK | Warning | Critical
        self.critical_sensors: List[Dict[str, Any]] = []

        # Raw collection error
        self.error: Optional[str] = None
        self.partial_collection = False


class RedfishCollector:
    """
    Async Redfish collector. One instance per server.

    Usage:
        async with RedfishCollector(bmc_ip, username, password) as collector:
            metrics = await collector.collect_all()
    """

    def __init__(
        self,
        server_id: str,
        bmc_ip: str,
        username: str,
        password: str,
        port: int = 443,
        verify_ssl: bool = False,  # Most datacenter BMCs use self-signed certs
        timeout: int = 30,
    ):
        self.server_id = server_id
        self.bmc_ip = bmc_ip
        self.username = username
        self.password = password
        self.port = port
        self.base_url = f"https://{bmc_ip}:{port}"
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.vendor: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        ssl_context = ssl.create_default_context() if self.verify_ssl else False
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=(self.username, self.password),
            verify=ssl_context,
            timeout=httpx.Timeout(self.timeout),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            # HTTP/2 is intentionally OFF and keepalive is disabled: HPE iLO closes each
            # connection after serving a request and drops concurrent HTTP/2 streams
            # ("Server disconnected without sending a response"), which silently zeroed out
            # thermal/power for ALL HPE hosts (→ false UNKNOWN). With keepalive off, httpx
            # opens a fresh connection per request instead of reusing a dead socket. Redfish
            # gains nothing from h2/keepalive here, and other BMCs are unaffected.
            http2=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    )
    async def _get(self, path: str) -> Dict[str, Any]:
        try:
            resp = await self._client.get(path)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            log.warning("redfish_http_error", path=path, status=e.response.status_code, server=self.bmc_ip)
            return {}
        except Exception as e:
            log.error("redfish_request_failed", path=path, error=str(e), server=self.bmc_ip)
            raise

    async def detect_vendor(self) -> str:
        """Detect vendor from Redfish root."""
        try:
            root = await self._get("/redfish/v1/")
            oem = root.get("Oem", {})
            if "Dell" in oem:
                self.vendor = RedfishVendor.DELL
            elif "Hpe" in oem or "Hp" in oem:
                self.vendor = RedfishVendor.HPE
            elif "Lenovo" in oem:
                self.vendor = RedfishVendor.LENOVO
            elif "Supermicro" in oem:
                self.vendor = RedfishVendor.SUPERMICRO
            elif "Amd" in oem or "AMD" in str(root):
                self.vendor = RedfishVendor.AMD
            else:
                self.vendor = RedfishVendor.GENERIC
        except Exception:
            self.vendor = RedfishVendor.GENERIC
        return self.vendor

    async def collect_all(self) -> RedfishMetrics:
        metrics = RedfishMetrics(self.server_id)
        try:
            await self.detect_vendor()
            metrics.vendor = self.vendor

            # Run all sub-collections concurrently
            results = await asyncio.gather(
                self._collect_system(metrics),
                self._collect_chassis(metrics),
                self._collect_power(metrics),
                self._collect_thermal(metrics),
                self._collect_storage(metrics),
                self._collect_network(metrics),
                self._collect_event_log(metrics),
                return_exceptions=True,
            )

            # Log any sub-collection errors without failing the whole collection
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    log.warning("redfish_subcollection_error", index=i, error=str(result), server=self.bmc_ip)
                    metrics.partial_collection = True

        except Exception as e:
            metrics.error = str(e)
            log.error("redfish_collection_failed", error=str(e), server=self.bmc_ip)

        return metrics

    async def _collect_system(self, metrics: RedfishMetrics) -> None:
        """Collect system identity, CPU, memory info."""
        systems_resp = await self._get("/redfish/v1/Systems")
        members = systems_resp.get("Members", [])
        if not members:
            return

        system_path = members[0].get("@odata.id", "")
        system = await self._get(system_path)

        metrics.model = system.get("Model")
        metrics.serial_number = system.get("SerialNumber")
        metrics.bios_version = system.get("BiosVersion")
        metrics.power_state = system.get("PowerState")
        metrics.indicator_led = system.get("IndicatorLED")
        metrics.location_indicator_active = system.get("LocationIndicatorActive")

        # CPU
        proc_summary = system.get("ProcessorSummary", {})
        metrics.cpu_count = proc_summary.get("Count")
        metrics.cpu_model = proc_summary.get("Model")
        if proc_summary.get("CoreCount"):
            metrics.cpu_cores_total = proc_summary.get("CoreCount")

        # Per-processor detail: model, cores, threads, microcode (Processors collection)
        proc_link = system.get("Processors", {}).get("@odata.id")
        if proc_link:
            try:
                proc_resp = await self._get(proc_link)
                members = proc_resp.get("Members", [])
                proc_tasks = [self._get(m["@odata.id"]) for m in members]
                procs_raw = await asyncio.gather(*proc_tasks, return_exceptions=True)
                cores_sum = 0
                threads_sum = 0
                for p in procs_raw:
                    if isinstance(p, Exception) or not p:
                        continue
                    # Only physical CPU sockets (skip GPUs/accelerators/FPGAs)
                    ptype = (p.get("ProcessorType") or "CPU")
                    if str(ptype).upper() not in ("CPU", ""):
                        continue
                    ucode = (p.get("ProcessorId", {}) or {}).get("MicrocodeInfo")
                    cores = p.get("TotalCores")
                    threads = p.get("TotalThreads")
                    pmodel = p.get("Model") or p.get("PartNumber")
                    metrics.processors.append({
                        "id": p.get("Id") or p.get("Socket") or p.get("Name"),
                        "model": str(pmodel).strip() if pmodel else None,
                        "cores": cores,
                        "threads": threads,
                        "microcode": str(ucode).strip() if ucode else None,
                        "speed_mhz": p.get("MaxSpeedMHz"),
                        "health": (p.get("Status", {}) or {}).get("Health"),
                    })
                    if cores:
                        cores_sum += int(cores)
                    if threads:
                        threads_sum += int(threads)
                    if metrics.microcode is None and ucode:
                        metrics.microcode = str(ucode).strip()

                if not metrics.cpu_count and members:
                    metrics.cpu_count = len([x for x in metrics.processors]) or len(members)
                if not metrics.cpu_model and metrics.processors:
                    metrics.cpu_model = next((x["model"] for x in metrics.processors if x.get("model")), None)
                if cores_sum and not metrics.cpu_cores_total:
                    metrics.cpu_cores_total = cores_sum
                if threads_sum:
                    metrics.cpu_threads_total = threads_sum
            except Exception as e:
                log.debug("processor_detail_failed", error=str(e), server=self.bmc_ip)

        # Memory
        mem_summary = system.get("MemorySummary", {})
        mem_gb = mem_summary.get("TotalSystemMemoryGiB")
        if mem_gb:
            metrics.memory_gb = int(mem_gb)

        # DIMMs
        memory_link = system.get("Memory", {}).get("@odata.id")
        if memory_link:
            mem_resp = await self._get(memory_link)
            dimm_tasks = [
                self._get(m["@odata.id"])
                for m in mem_resp.get("Members", [])
            ]
            dimms_raw = await asyncio.gather(*dimm_tasks, return_exceptions=True)
            for dimm in dimms_raw:
                if isinstance(dimm, Exception) or not dimm:
                    continue
                metrics.dimms.append({
                    "name": dimm.get("DeviceLocator") or dimm.get("Id") or dimm.get("Name"),
                    "capacity_gb": dimm.get("CapacityMiB", 0) // 1024,
                    "speed_mhz": dimm.get("OperatingSpeedMhz"),
                    "manufacturer": dimm.get("Manufacturer"),
                    "part_number": dimm.get("PartNumber"),
                    "serial_number": dimm.get("SerialNumber"),
                    "dimm_type": dimm.get("MemoryDeviceType"),
                    "status": dimm.get("Status", {}).get("Health", "Unknown"),
                    "populated": dimm.get("CapacityMiB", 0) > 0,
                })

    async def _collect_chassis(self, metrics: RedfishMetrics) -> None:
        """Collect chassis-level info and BMC firmware."""
        managers_resp = await self._get("/redfish/v1/Managers")
        members = managers_resp.get("Members", [])
        if members:
            manager = await self._get(members[0]["@odata.id"])
            metrics.bmc_firmware = manager.get("FirmwareVersion")

        # Collect chassis indicator LED
        chassis_resp = await self._get("/redfish/v1/Chassis")
        chassis_members = chassis_resp.get("Members", [])
        if chassis_members:
            chassis_path = chassis_members[0].get("@odata.id")
            if chassis_path:
                chassis = await self._get(chassis_path)
                metrics.chassis_led = chassis.get("IndicatorLED") or chassis.get("LocationIndicatorActive")

    async def _collect_power(self, metrics: RedfishMetrics) -> None:
        """Collect power consumption and PSU status."""
        chassis_resp = await self._get("/redfish/v1/Chassis")
        chassis_members = chassis_resp.get("Members", [])
        if not chassis_members:
            return

        chassis = await self._get(chassis_members[0]["@odata.id"])
        power_link = chassis.get("Power", {}).get("@odata.id")
        if not power_link:
            return

        power = await self._get(power_link)

        # Aggregate power supplies
        total_capacity = 0
        total_consumed = 0

        for psu in power.get("PowerSupplies", []):
            capacity = psu.get("PowerCapacityWatts", 0) or 0
            total_capacity += capacity
            metrics.psus.append({
                "name": psu.get("Name"),
                "model": psu.get("Model"),
                "serial_number": psu.get("SerialNumber"),
                "capacity_watts": capacity,
                "current_watts": psu.get("LastPowerOutputWatts"),
                "voltage": psu.get("LineInputVoltage"),
                "status": psu.get("Status", {}).get("Health", "Unknown"),
                "present": psu.get("Status", {}).get("State") != "Absent",
            })

        # Power control (actual consumption). Reject BMC sentinel/garbage values
        # (negative or absurdly large) so a single bad reading can't poison totals.
        for pc in power.get("PowerControl", []):
            consumed = pc.get("PowerConsumedWatts")
            if consumed is not None and 0 < consumed < 50000:
                total_consumed += consumed
            # Get capacity from PowerLimit if not from PSUs
            limit = pc.get("PowerLimit", {})
            if limit and not total_capacity:
                total_capacity = limit.get("LimitInWatts", 0)

        # AMD EPYC CRB / OpenBMC fallback: legacy Power object is often empty —
        # power lives in the modern Sensors collection as per-rail *_POUT readings.
        if not total_consumed:
            try:
                rail_power = await self._collect_power_sensors(chassis)
                if rail_power:
                    total_consumed = rail_power
            except Exception as e:
                log.debug("power_sensor_fallback_failed", error=str(e), server=self.bmc_ip)

        metrics.power_consumed_watts = total_consumed if total_consumed else None
        metrics.power_capacity_watts = total_capacity if total_capacity else None

    async def _collect_power_sensors(self, chassis: Dict[str, Any]) -> Optional[float]:
        """Sum per-rail power output (*_POUT) from the Sensors collection (AMD CRB/OpenBMC)."""
        sensors_link = chassis.get("Sensors", {}).get("@odata.id")
        if not sensors_link:
            return None

        sensors_coll = await self._get(sensors_link)
        members = sensors_coll.get("Members", [])
        # Match per-rail power-out sensors: "_POUT" (volcano/turin) and "_POUTn" (genoa, e.g. _POUT1)
        import re
        pout_links = [
            m["@odata.id"] for m in members
            if re.search(r"_POUT\d*$", m.get("@odata.id", ""), re.IGNORECASE)
        ]
        if not pout_links:
            return None

        readings = await asyncio.gather(
            *[self._get(link) for link in pout_links], return_exceptions=True
        )
        total = 0.0
        found = False
        for r in readings:
            if isinstance(r, Exception) or not r:
                continue
            val = r.get("Reading")
            units = str(r.get("ReadingUnits", "")).lower()
            if val is not None and ("watt" in units or units == "w" or units == ""):
                total += float(val)
                found = True
        return round(total, 1) if found else None

    async def _collect_thermal(self, metrics: RedfishMetrics) -> None:
        """Collect temperature/fan status across ALL chassis + their sub-chassis.

        Newer AMD CRBs expose Thermal on the first chassis; older Milan boards keep
        an empty RackMount chassis and put sensors on a Baseboard sub-chassis. We
        scan every chassis member and any linked/contained sub-chassis.
        """
        chassis_resp = await self._get("/redfish/v1/Chassis")
        chassis_members = chassis_resp.get("Members", [])
        if not chassis_members:
            return

        visited: set[str] = set()
        # Seed with top-level chassis paths
        to_visit = [m["@odata.id"] for m in chassis_members if m.get("@odata.id")]

        idx = 0
        while idx < len(to_visit):
            path = to_visit[idx]
            idx += 1
            if path in visited:
                continue
            visited.add(path)

            chassis = await self._get(path)
            if not chassis:
                continue

            # Queue linked/contained sub-chassis (e.g. RackMount -> Baseboard)
            contains = chassis.get("Links", {}).get("Contains", [])
            for c in contains:
                cid = c.get("@odata.id")
                if cid and cid not in visited:
                    to_visit.append(cid)

            thermal_link = chassis.get("Thermal", {}).get("@odata.id")
            if not thermal_link:
                continue
            thermal = await self._get(thermal_link)
            if not thermal:
                continue
            self._parse_thermal(thermal, metrics)

    @staticmethod
    def _is_sentinel(reading, warn, crit):
        """Absent/disabled sensors report sentinel values (-1, 0, 0.0) that the BMC may
        still mark Critical. Treat reading <= 0 as 'not present' so we don't false-alarm.
        Real temp faults are always positive and at/above their threshold."""
        if reading is None:
            return True
        try:
            r = float(reading)
        except (TypeError, ValueError):
            return True
        if r <= 0:
            return True
        # a reading that is positive but nowhere near its own thresholds is not a real fault
        if crit is not None and r < float(crit) and warn is not None and r < float(warn):
            return False  # below both thresholds → handled by health verdict, not sentinel
        return False

    # Hysteresis deadband (°C): a sensor reading must exceed its threshold by this
    # margin before we treat it as Warning/Critical. Without it, a reading sitting
    # right at its threshold (e.g. outlet temp 31.5 vs warn 30) oscillates OK↔Warning
    # every collection cycle and flaps the server's status (changelog/dashboard churn).
    SENSOR_WARN_MARGIN = 2.0
    SENSOR_CRIT_MARGIN = 2.0

    @classmethod
    def _effective_health(cls, reading, warn, crit, health):
        """Use BMC-reported Health, but suppress false positives from absent sensors
        (sentinel readings <= 0) and borderline readings within a hysteresis margin.
        Fall back to threshold derivation when Health absent."""
        # Sentinel / not-present sensor → never a real fault
        if cls._is_sentinel(reading, warn, crit):
            return "OK"
        try:
            r = float(reading)
        except (TypeError, ValueError):
            return health if health in ("Critical", "Warning", "OK") else "OK"

        # Effective thresholds include the deadband margin so a reading hovering at the
        # raw threshold does not flip state every cycle.
        warn_eff = (float(warn) + cls.SENSOR_WARN_MARGIN) if warn is not None else None
        crit_eff = (float(crit) + cls.SENSOR_CRIT_MARGIN) if crit is not None else None

        if health in ("Critical", "Warning", "OK"):
            # Trust BMC verdict, but only if the reading clears the margin-adjusted
            # threshold (guards against stale/borderline flags that just flap).
            if health == "Critical":
                if crit_eff is not None and r >= crit_eff:
                    return "Critical"
                if warn_eff is not None and r >= warn_eff:
                    return "Warning"
                return "OK"
            if health == "Warning":
                if warn_eff is not None and r >= warn_eff:
                    return "Warning"
                # also honor an unflagged but margin-clearing critical
                if crit_eff is not None and r >= crit_eff:
                    return "Critical"
                return "OK"
            return "OK"
        if crit_eff is not None and r >= crit_eff:
            return "Critical"
        if warn_eff is not None and r >= warn_eff:
            return "Warning"
        return "OK"

    def _escalate(self, metrics: RedfishMetrics, state: str, name, reading, warn, crit):
        rank = {"OK": 0, "Warning": 1, "Critical": 2}
        cur = rank.get(metrics.sensor_health or "OK", 0)
        if rank.get(state, 0) > cur:
            metrics.sensor_health = state
        if state in ("Warning", "Critical"):
            metrics.critical_sensors.append({
                "name": name, "reading": reading, "warn": warn, "crit": crit, "state": state,
            })

    def _parse_thermal(self, thermal: Dict[str, Any], metrics: RedfishMetrics) -> None:
        for temp in thermal.get("Temperatures", []):
            reading = temp.get("ReadingCelsius")
            if reading is None:
                continue
            name = temp.get("Name", "").lower()
            warn = temp.get("UpperThresholdNonCritical")
            crit = temp.get("UpperThresholdCritical")
            health = temp.get("Status", {}).get("Health")
            metrics.temperatures.append({
                "name": temp.get("Name"),
                "reading": reading,
                "upper_warning": warn,
                "upper_critical": crit,
                "status": health,
                "physical_context": temp.get("PhysicalContext"),
            })
            # Honor the BMC's own verdict for this sensor
            state = self._effective_health(reading, warn, crit, health)
            self._escalate(metrics, state, temp.get("Name"), reading, warn, crit)

            if "inlet" in name or "ambient" in name or "system board" in name:
                metrics.inlet_temp = reading
            elif "exhaust" in name or "outlet" in name:
                metrics.outlet_temp = reading
            elif "cpu" in name or "processor" in name or "soc" in name:
                metrics.cpu_temps.append(reading)

        for fan in thermal.get("Fans", []):
            fhealth = fan.get("Status", {}).get("Health")
            metrics.fans.append({
                "name": fan.get("Name"),
                "rpm": fan.get("Reading"),
                "status": fhealth,
                "failed": fan.get("Status", {}).get("State") == "UnavailableOffline",
            })
            # Only escalate a fan if it's actually marked failed (state) — many BMCs flag
            # absent water-pump/optional fans as Critical with reading 0 (false positive).
            if fan.get("Status", {}).get("State") == "UnavailableOffline" and fhealth == "Critical":
                self._escalate(metrics, "Critical", fan.get("Name"), fan.get("Reading"), None, None)

    async def _collect_storage(self, metrics: RedfishMetrics) -> None:
        """Collect disk and RAID status."""
        storage_resp = await self._get("/redfish/v1/Systems")
        systems = storage_resp.get("Members", [])
        if not systems:
            return

        system = await self._get(systems[0]["@odata.id"])
        storage_link = system.get("Storage", {}).get("@odata.id")
        if not storage_link:
            return

        storage_coll = await self._get(storage_link)
        controller_tasks = [
            self._get(m["@odata.id"])
            for m in storage_coll.get("Members", [])
        ]
        controllers = await asyncio.gather(*controller_tasks, return_exceptions=True)

        for ctrl in controllers:
            if isinstance(ctrl, Exception) or not ctrl:
                continue

            # Drives
            drive_tasks = [
                self._get(d["@odata.id"])
                for d in ctrl.get("Drives", [])
            ]
            drives_raw = await asyncio.gather(*drive_tasks, return_exceptions=True)
            for drv in drives_raw:
                if isinstance(drv, Exception) or not drv:
                    continue
                cap_bytes = drv.get("CapacityBytes", 0) or 0
                metrics.drives.append({
                    "name": drv.get("Name"),
                    "model": drv.get("Model"),
                    "serial_number": drv.get("SerialNumber"),
                    "capacity_gb": cap_bytes // (1024 ** 3),
                    "protocol": drv.get("Protocol"),
                    "media_type": drv.get("MediaType"),
                    "firmware_version": drv.get("Revision"),
                    "status": drv.get("Status", {}).get("Health"),
                    "failure_predicted": drv.get("FailurePredicted", False),
                    "predicted_media_life_left_pct": drv.get("PredictedMediaLifeLeftPercent"),
                    "read_errors": drv.get("ReadErrors"),
                    "write_errors": drv.get("WriteErrors"),
                })

            # Volumes
            volumes_link = ctrl.get("Volumes", {}).get("@odata.id")
            if volumes_link:
                vol_coll = await self._get(volumes_link)
                vol_tasks = [self._get(v["@odata.id"]) for v in vol_coll.get("Members", [])]
                vols = await asyncio.gather(*vol_tasks, return_exceptions=True)
                for vol in vols:
                    if isinstance(vol, Exception) or not vol:
                        continue
                    metrics.volumes.append({
                        "name": vol.get("Name"),
                        "raid_type": vol.get("RAIDType"),
                        "status": vol.get("Status", {}).get("Health"),
                        "capacity_gb": (vol.get("CapacityBytes", 0) or 0) // (1024 ** 3),
                        "optimum": vol.get("Status", {}).get("Health") == "OK",
                    })

    async def _collect_network(self, metrics: RedfishMetrics) -> None:
        """Collect NIC status and link information."""
        systems_resp = await self._get("/redfish/v1/Systems")
        systems = systems_resp.get("Members", [])
        if not systems:
            return

        system = await self._get(systems[0]["@odata.id"])
        net_link = system.get("EthernetInterfaces", {}).get("@odata.id")
        if not net_link:
            return

        net_coll = await self._get(net_link)
        nic_tasks = [self._get(m["@odata.id"]) for m in net_coll.get("Members", [])]
        nics_raw = await asyncio.gather(*nic_tasks, return_exceptions=True)

        for nic in nics_raw:
            if isinstance(nic, Exception) or not nic:
                continue
            # BMCs report link state inconsistently (LinkUp / Up / Enabled / LinkDown /
            # Disabled / absent). Normalize to canonical "Up"/"Down" at the source so the
            # whole app reads one value. Fall back to Status.State when LinkStatus is absent.
            raw_link = nic.get("LinkStatus") or nic.get("Status", {}).get("State")
            link = _canon_link(raw_link)
            metrics.nics.append({
                "name": nic.get("Name"),
                "mac_address": nic.get("MACAddress"),
                "link_status": link,
                "speed_mbps": nic.get("SpeedMbps"),
                "ip_addresses": [
                    addr.get("Address")
                    for addr in nic.get("IPv4Addresses", [])
                    if addr.get("Address")
                ],
            })

    async def _collect_event_log(self, metrics: RedfishMetrics) -> None:
        """Collect recent System Event Log (SEL) entries."""
        try:
            logs_resp = await self._get("/redfish/v1/Managers")
            managers = logs_resp.get("Members", [])
            if not managers:
                return

            manager = await self._get(managers[0]["@odata.id"])
            log_services_link = manager.get("LogServices", {}).get("@odata.id")
            if not log_services_link:
                return

            log_services = await self._get(log_services_link)
            log_members = log_services.get("Members", [])
            if not log_members:
                return

            # Get most recent log entries
            log_service = await self._get(log_members[0]["@odata.id"])
            entries_link = log_service.get("Entries", {}).get("@odata.id")
            if not entries_link:
                return

            entries_resp = await self._get(f"{entries_link}?$top=20&$orderby=Created desc")
            for entry in entries_resp.get("Members", [])[:20]:
                metrics.sel_events.append({
                    "id": entry.get("Id"),
                    "message": entry.get("Message"),
                    "severity": entry.get("Severity"),
                    "created": entry.get("Created"),
                    "category": entry.get("MessageId"),
                })
        except Exception as e:
            log.debug("sel_collection_skipped", error=str(e), server=self.bmc_ip)


class FleetRedfishCollector:
    """
    Manages concurrent Redfish collection across the entire fleet.
    Respects rate limits and handles credential lookup from Vault.
    """

    def __init__(self, credential_provider):
        self.credential_provider = credential_provider
        self.semaphore = asyncio.Semaphore(settings.REDFISH_CONCURRENT_LIMIT)

    async def collect_server(self, server) -> RedfishMetrics:
        """Collect from a single server with semaphore throttling."""
        async with self.semaphore:
            creds = await self.credential_provider.get_credentials(server.id, server=server)
            if not creds:
                metrics = RedfishMetrics(server.id)
                metrics.error = "No credentials available"
                return metrics

            async with RedfishCollector(
                server_id=server.id,
                bmc_ip=server.bmc_ip,
                username=creds["username"],
                password=creds["password"],
                port=server.bmc_port or 443,
            ) as collector:
                return await collector.collect_all()

    async def collect_fleet(self, servers: list) -> List[RedfishMetrics]:
        """Collect from all servers concurrently."""
        tasks = [self.collect_server(s) for s in servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if isinstance(r, RedfishMetrics) else RedfishMetrics(servers[i].id)
            for i, r in enumerate(results)
        ]
