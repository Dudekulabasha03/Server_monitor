"""
IPMI Collector — uses ipmitool subprocess + python-ipmi for sensor data.
Fallback for servers where Redfish is unavailable or incomplete.
"""
import asyncio
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import structlog

log = structlog.get_logger(__name__)


class IPMIMetrics:
    def __init__(self, server_id: str):
        self.server_id = server_id
        self.collected_at = datetime.now(timezone.utc)
        self.temperatures: List[Dict[str, Any]] = []
        self.voltages: List[Dict[str, Any]] = []
        self.fans: List[Dict[str, Any]] = []
        self.power: List[Dict[str, Any]] = []
        self.chassis_status: Dict[str, Any] = {}
        self.sel_events: List[Dict[str, Any]] = []
        self.error: Optional[str] = None


class IPMICollector:
    """
    Async IPMI collector using ipmitool subprocess.

    Requires ipmitool installed on the collector host.
    Uses IPMI over LAN (cipher suite 17 recommended).
    """

    IPMITOOL_PATH = "ipmitool"

    def __init__(
        self,
        server_id: str,
        ipmi_ip: str,
        username: str,
        password: str,
        port: int = 623,
        cipher_suite: int = 17,
        timeout: int = 10,
    ):
        self.server_id = server_id
        self.ipmi_ip = ipmi_ip
        self.username = username
        self.password = password
        self.port = port
        self.cipher_suite = cipher_suite
        self.timeout = timeout

    def _base_cmd(self) -> List[str]:
        return [
            self.IPMITOOL_PATH,
            "-I", "lanplus",
            "-H", self.ipmi_ip,
            "-U", self.username,
            "-P", self.password,
            "-p", str(self.port),
            "-C", str(self.cipher_suite),
        ]

    async def _run_command(self, *args: str) -> str:
        """Execute ipmitool command asynchronously."""
        cmd = self._base_cmd() + list(args)
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self.timeout,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            if proc.returncode != 0:
                log.warning("ipmi_command_error", cmd=args, stderr=stderr.decode(), host=self.ipmi_ip)
                return ""
            return stdout.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            log.warning("ipmi_timeout", cmd=args, host=self.ipmi_ip)
            return ""
        except FileNotFoundError:
            log.error("ipmitool_not_found")
            return ""
        except Exception as e:
            log.error("ipmi_command_failed", error=str(e), host=self.ipmi_ip)
            return ""

    def _parse_sensor_dump(self, output: str) -> List[Dict[str, Any]]:
        """Parse `ipmitool sdr type` or `ipmitool sensor` output."""
        sensors = []
        for line in output.splitlines():
            # Format: Name | Value | Unit | Status | Lower NR | Lower C | Lower NC | Upper NC | Upper C | Upper NR
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue
            name = parts[0].strip()
            value_str = parts[1].strip()
            unit = parts[2].strip() if len(parts) > 2 else ""
            status = parts[3].strip() if len(parts) > 3 else ""

            value = None
            if value_str and value_str.lower() not in ("no reading", "disabled", "na", "n/a"):
                try:
                    value = float(value_str)
                except ValueError:
                    value = None

            sensors.append({
                "name": name,
                "value": value,
                "unit": unit,
                "status": status,
                "upper_critical": self._safe_float(parts[8]) if len(parts) > 8 else None,
                "upper_warning": self._safe_float(parts[7]) if len(parts) > 7 else None,
            })
        return sensors

    @staticmethod
    def _safe_float(s: str) -> Optional[float]:
        try:
            return float(s.strip())
        except (ValueError, AttributeError):
            return None

    def _parse_sel(self, output: str) -> List[Dict[str, Any]]:
        """Parse `ipmitool sel elist` output."""
        events = []
        for line in output.splitlines()[:50]:  # last 50 entries
            # Format: ID | Date | Time | Name | Type | Direction | Description
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 6:
                continue
            events.append({
                "id": parts[0],
                "date": parts[1],
                "time": parts[2],
                "name": parts[3],
                "type": parts[4],
                "direction": parts[5],
                "description": parts[6] if len(parts) > 6 else "",
            })
        return events

    def _parse_chassis_status(self, output: str) -> Dict[str, Any]:
        status: Dict[str, Any] = {}
        for line in output.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                status[key.strip().lower().replace(" ", "_")] = value.strip()
        return status

    async def collect_all(self) -> IPMIMetrics:
        metrics = IPMIMetrics(self.server_id)
        try:
            # Run collections concurrently
            sensor_out, chassis_out, sel_out = await asyncio.gather(
                self._run_command("sensor"),
                self._run_command("chassis", "status"),
                self._run_command("sel", "elist"),
                return_exceptions=True,
            )

            if isinstance(sensor_out, str) and sensor_out:
                all_sensors = self._parse_sensor_dump(sensor_out)
                for s in all_sensors:
                    unit = s.get("unit", "").lower()
                    name = s.get("name", "").lower()
                    if "degrees c" in unit or "celsius" in unit:
                        metrics.temperatures.append(s)
                    elif "volts" in unit or "voltage" in unit:
                        metrics.voltages.append(s)
                    elif "rpm" in unit:
                        metrics.fans.append(s)
                    elif "watts" in unit:
                        metrics.power.append(s)

            if isinstance(chassis_out, str) and chassis_out:
                metrics.chassis_status = self._parse_chassis_status(chassis_out)

            if isinstance(sel_out, str) and sel_out:
                metrics.sel_events = self._parse_sel(sel_out)

        except Exception as e:
            metrics.error = str(e)
            log.error("ipmi_collection_failed", error=str(e), host=self.ipmi_ip)

        return metrics


class IPMIFleetCollector:
    """Manages concurrent IPMI collection across the fleet."""

    def __init__(self, credential_provider, max_concurrent: int = 30):
        self.credential_provider = credential_provider
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def collect_server(self, server) -> IPMIMetrics:
        async with self.semaphore:
            creds = await self.credential_provider.get_credentials(server.id, server=server)
            if not creds:
                metrics = IPMIMetrics(server.id)
                metrics.error = "No credentials"
                return metrics

            collector = IPMICollector(
                server_id=server.id,
                ipmi_ip=server.ipmi_ip or server.bmc_ip,
                username=creds["username"],
                password=creds["password"],
            )
            return await collector.collect_all()
