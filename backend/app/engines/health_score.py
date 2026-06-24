"""
Health Score Engine — calculates 0-100 health score from collected metrics.

Weights:
  Hardware    30%
  Thermal     20%
  Power       10%
  Storage     15%
  Network     10%
  Utilization 15%
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from app.config import settings


@dataclass
class ScoreDeduction:
    component: str
    reason: str
    points: float
    severity: str  # warning | critical


@dataclass
class HealthScoreResult:
    total_score: float
    status: str  # healthy | warning | at_risk | critical

    hardware_score: float = 100.0
    thermal_score: float = 100.0
    power_score: float = 100.0
    storage_score: float = 100.0
    network_score: float = 100.0
    utilization_score: float = 100.0

    hardware_contribution: float = 0.0
    thermal_contribution: float = 0.0
    power_contribution: float = 0.0
    storage_contribution: float = 0.0
    network_contribution: float = 0.0
    utilization_contribution: float = 0.0

    deductions: List[ScoreDeduction] = field(default_factory=list)

    @property
    def deductions_as_dicts(self) -> List[Dict[str, Any]]:
        return [{"component": d.component, "reason": d.reason, "points": d.points, "severity": d.severity}
                for d in self.deductions]


def _score_to_status(score: float, deductions: list | None = None) -> str:
    """Convert numeric score to status, with override for hard failures.

    Any critical deduction (PSU/fan failure, critical temperature, sensor
    critical) forces at minimum 'at_risk' regardless of score.
    Multiple critical deductions force 'critical'.
    """
    if deductions:
        critical_count = sum(1 for d in deductions if d.severity == "critical")
        if critical_count >= 2:
            return "critical"
        if critical_count == 1:
            # One critical deduction: override down to at_risk minimum
            if score >= 90:
                return "at_risk"

    if score >= 90:
        return "healthy"
    elif score >= 75:
        return "warning"
    elif score >= 50:
        return "at_risk"
    return "critical"


class HealthScoreEngine:
    """
    Calculates health score from a MetricsSnapshot and component data.

    All sub-scores start at 100 and deductions are applied.
    """

    def calculate(self, snapshot, server, dimms=None, disks=None, psus=None, nics=None) -> HealthScoreResult:
        deductions: List[ScoreDeduction] = []

        hardware_score = self._score_hardware(server, dimms, psus, deductions, snapshot=snapshot)
        thermal_score = self._score_thermal(snapshot, deductions)
        power_score = self._score_power(snapshot, psus, deductions)
        storage_score = self._score_storage(snapshot, disks, deductions)
        network_score = self._score_network(snapshot, nics, deductions)
        utilization_score = self._score_utilization(snapshot, deductions)

        w = settings
        hw = hardware_score * w.HEALTH_WEIGHT_HARDWARE
        th = thermal_score * w.HEALTH_WEIGHT_THERMAL
        pw = power_score * w.HEALTH_WEIGHT_POWER
        st = storage_score * w.HEALTH_WEIGHT_STORAGE
        nw = network_score * w.HEALTH_WEIGHT_NETWORK
        ut = utilization_score * w.HEALTH_WEIGHT_UTILIZATION

        total = hw + th + pw + st + nw + ut

        result = HealthScoreResult(
            total_score=round(total, 1),
            status=_score_to_status(total, deductions),
            hardware_score=round(hardware_score, 1),
            thermal_score=round(thermal_score, 1),
            power_score=round(power_score, 1),
            storage_score=round(storage_score, 1),
            network_score=round(network_score, 1),
            utilization_score=round(utilization_score, 1),
            hardware_contribution=round(hw, 1),
            thermal_contribution=round(th, 1),
            power_contribution=round(pw, 1),
            storage_contribution=round(st, 1),
            network_contribution=round(nw, 1),
            utilization_contribution=round(ut, 1),
            deductions=deductions,
        )
        return result

    def _score_hardware(self, server, dimms, psus, deductions: List[ScoreDeduction],
                        snapshot=None) -> HealthScoreResult:
        score = 100.0

        # BMC unreachable
        if server.status and server.status.value == "offline":
            deductions.append(ScoreDeduction("hardware", "Server offline / BMC unreachable", 100, "critical"))
            return 0.0

        # DIMM errors
        if dimms:
            failed_dimms = [d for d in dimms if d.health and d.health.lower() in ("critical", "warning")]
            for dimm in failed_dimms:
                sev = "critical" if dimm.health.lower() == "critical" else "warning"
                pts = 30 if sev == "critical" else 10
                deductions.append(ScoreDeduction("hardware", f"DIMM {dimm.slot_name} {dimm.health}", pts, sev))
                score -= pts

        # PSU failures — prefer psus table, fall back to snapshot.psu_failed_count
        if psus:
            failed_psus = [p for p in psus if not p.present or (p.health and p.health.lower() == "critical")]
            for psu in failed_psus:
                deductions.append(ScoreDeduction("hardware", f"PSU {psu.slot} failed/absent", 25, "critical"))
                score -= 25
        elif snapshot and snapshot.psu_failed_count:
            n = snapshot.psu_failed_count
            if n >= 2:
                # Multiple PSU failures — power loss imminent
                deductions.append(ScoreDeduction("hardware",
                    f"{n} PSUs failed — power loss risk", 50, "critical"))
                score -= 50
            elif n == 1:
                # Single PSU — redundancy lost, urgent replacement needed
                deductions.append(ScoreDeduction("hardware",
                    "1 PSU failed — redundancy lost", 25, "critical"))
                score -= 25

        # Fan failures from snapshot (supplement thermal score with hardware deduction)
        if snapshot and snapshot.fan_failed_count and snapshot.fan_failed_count > 0:
            n = snapshot.fan_failed_count
            if n >= 3:
                deductions.append(ScoreDeduction("hardware",
                    f"{n} fans failed — critical cooling risk", 40, "critical"))
                score -= 40
            elif n >= 2:
                deductions.append(ScoreDeduction("hardware",
                    f"{n} fans failed — reduced cooling", 25, "critical"))
                score -= 25
            else:
                deductions.append(ScoreDeduction("hardware",
                    f"1 fan failed — monitor cooling", 10, "warning"))
                score -= 10

        # Firmware compliance
        if server.firmware_baseline_compliant is False:
            deductions.append(ScoreDeduction("hardware", "Firmware not compliant with baseline", 10, "warning"))
            score -= 10

        # Warranty expired
        from datetime import datetime, timezone
        if server.warranty_expiry and server.warranty_expiry < datetime.now(timezone.utc):
            deductions.append(ScoreDeduction("hardware", "Warranty expired", 5, "warning"))
            score -= 5

        return max(0.0, score)

    def _score_thermal(self, snapshot, deductions: List[ScoreDeduction]) -> float:
        if not snapshot:
            return 50.0  # Unknown = penalize moderately

        score = 100.0

        # CPU temperature
        cpu_temp = snapshot.cpu_temp_max
        if cpu_temp is not None:
            if cpu_temp >= settings.TEMP_CPU_CRITICAL:
                pts = 40
                deductions.append(ScoreDeduction("thermal", f"CPU temp {cpu_temp:.1f}°C >= {settings.TEMP_CPU_CRITICAL}°C", pts, "critical"))
                score -= pts
            elif cpu_temp >= settings.TEMP_CPU_WARNING:
                pts = 20
                deductions.append(ScoreDeduction("thermal", f"CPU temp {cpu_temp:.1f}°C >= {settings.TEMP_CPU_WARNING}°C", pts, "warning"))
                score -= pts

        # Inlet temperature
        inlet = snapshot.inlet_temp
        if inlet is not None:
            if inlet >= settings.TEMP_INLET_CRITICAL:
                pts = 30
                deductions.append(ScoreDeduction("thermal", f"Inlet temp {inlet:.1f}°C >= {settings.TEMP_INLET_CRITICAL}°C (datacenter cooling issue)", pts, "critical"))
                score -= pts
            elif inlet >= settings.TEMP_INLET_WARNING:
                pts = 15
                deductions.append(ScoreDeduction("thermal", f"Inlet temp {inlet:.1f}°C >= {settings.TEMP_INLET_WARNING}°C", pts, "warning"))
                score -= pts

        # Fan failures
        if snapshot.fan_failed_count and snapshot.fan_failed_count > 0:
            pts = 30 if snapshot.fan_failed_count > 1 else 15
            deductions.append(ScoreDeduction("thermal", f"{snapshot.fan_failed_count} fan(s) failed", pts, "critical"))
            score -= pts

        # BMC-declared sensor health — trust the BMC's own verdict on ANY sensor
        sh = getattr(snapshot, "sensor_health", None)
        if sh in ("Critical", "Warning"):
            offenders = []
            raw = getattr(snapshot, "raw_sensors", None) or {}
            for cs in (raw.get("critical_sensors") or [])[:4]:
                nm = cs.get("name")
                rd = cs.get("reading")
                lim = cs.get("crit") if cs.get("state") == "Critical" else cs.get("warn")
                offenders.append(f"{nm} {rd}°C" + (f"≥{lim}°C" if lim is not None else ""))
            names = "; ".join(offenders) if offenders else "BMC sensor(s)"
            if sh == "Critical":
                pts = 40
                deductions.append(ScoreDeduction("thermal", f"BMC sensor CRITICAL: {names}", pts, "critical"))
            else:
                pts = 15
                deductions.append(ScoreDeduction("thermal", f"BMC sensor warning: {names}", pts, "warning"))
            score -= pts

        return max(0.0, score)

    def _score_power(self, snapshot, psus, deductions: List[ScoreDeduction]) -> float:
        if not snapshot:
            return 50.0

        score = 100.0

        # Power headroom
        if snapshot.power_consumed_watts and snapshot.power_capacity_watts:
            ratio = snapshot.power_consumed_watts / snapshot.power_capacity_watts
            if ratio >= 0.95:
                deductions.append(ScoreDeduction("power", f"Power draw at {ratio*100:.0f}% of PSU capacity (critical headroom)", 40, "critical"))
                score -= 40
            elif ratio >= settings.POWER_HEADROOM_WARNING:
                deductions.append(ScoreDeduction("power", f"Power draw at {ratio*100:.0f}% of PSU capacity", 20, "warning"))
                score -= 20

        # PSU redundancy: psus table first, then snapshot count as fallback
        if psus:
            failed_count = sum(1 for p in psus if not p.present)
            total_count = len(psus)
            if failed_count >= 2:
                deductions.append(ScoreDeduction("power",
                    f"Multiple PSU failures ({failed_count}/{total_count}) — power loss risk", 35, "critical"))
                score -= 35
            elif failed_count == 1 and total_count > 1:
                deductions.append(ScoreDeduction("power",
                    f"PSU redundancy lost ({failed_count}/{total_count} PSUs failed)", 20, "warning"))
                score -= 20
        elif snapshot.psu_failed_count and snapshot.psu_failed_count > 0:
            n = snapshot.psu_failed_count
            # Already deducted in hardware — add smaller power-domain deduction
            if n >= 2:
                deductions.append(ScoreDeduction("power",
                    f"Power subsystem critical: {n} PSUs failed", 30, "critical"))
                score -= 30
            else:
                deductions.append(ScoreDeduction("power",
                    "Power redundancy lost: 1 PSU failed", 15, "warning"))
                score -= 15

        return max(0.0, score)

    def _score_storage(self, snapshot, disks, deductions: List[ScoreDeduction]) -> float:
        if not snapshot and not disks:
            return 50.0

        score = 100.0

        # Disk usage
        if snapshot and snapshot.disk_usage_max_pct is not None:
            usage = snapshot.disk_usage_max_pct
            if usage >= settings.DISK_USAGE_CRITICAL:
                deductions.append(ScoreDeduction("storage", f"Disk usage at {usage:.0f}% (critically full)", 35, "critical"))
                score -= 35
            elif usage >= settings.DISK_USAGE_WARNING:
                deductions.append(ScoreDeduction("storage", f"Disk usage at {usage:.0f}%", 15, "warning"))
                score -= 15

        # Disk health / SMART
        if disks:
            failed = [d for d in disks if d.health and d.health.lower() == "critical"]
            predicted_fail = [d for d in disks if d.failure_predicted]
            bad_smart = [d for d in disks if d.smart_status and d.smart_status.lower() != "ok"]

            for d in failed:
                deductions.append(ScoreDeduction("storage", f"Disk {d.slot or d.name} health CRITICAL", 40, "critical"))
                score -= 40

            for d in predicted_fail:
                deductions.append(ScoreDeduction("storage", f"Disk {d.slot or d.name} failure predicted (SMART)", 30, "critical"))
                score -= 30

            for d in bad_smart:
                if d not in predicted_fail:
                    deductions.append(ScoreDeduction("storage", f"Disk {d.slot or d.name} SMART warning", 10, "warning"))
                    score -= 10

        return max(0.0, score)

    def _score_network(self, snapshot, nics, deductions: List[ScoreDeduction]) -> float:
        score = 100.0

        if snapshot and snapshot.net_errors_total and snapshot.net_errors_total > 100:
            deductions.append(ScoreDeduction("network", f"High network error count: {snapshot.net_errors_total}", 20, "warning"))
            score -= 20

        # NIC link down
        if nics:
            down_nics = [n for n in nics if n.link_status and n.link_status.lower() != "up"]
            for nic in down_nics:
                deductions.append(ScoreDeduction("network", f"NIC {nic.name} link down", 15, "warning"))
                score -= 15

        return max(0.0, score)

    def _score_utilization(self, snapshot, deductions: List[ScoreDeduction]) -> float:
        if not snapshot:
            return 50.0

        score = 100.0

        # CPU
        cpu = snapshot.cpu_usage_avg
        if cpu is not None:
            if cpu >= settings.CPU_USAGE_CRITICAL:
                deductions.append(ScoreDeduction("utilization", f"CPU usage {cpu:.0f}% (critical)", 30, "critical"))
                score -= 30
            elif cpu >= settings.CPU_USAGE_WARNING:
                deductions.append(ScoreDeduction("utilization", f"CPU usage {cpu:.0f}%", 15, "warning"))
                score -= 15

        # Memory
        mem = snapshot.memory_usage_pct
        if mem is not None:
            if mem >= settings.MEM_USAGE_CRITICAL:
                deductions.append(ScoreDeduction("utilization", f"Memory usage {mem:.0f}% (critical)", 30, "critical"))
                score -= 30
            elif mem >= settings.MEM_USAGE_WARNING:
                deductions.append(ScoreDeduction("utilization", f"Memory usage {mem:.0f}%", 15, "warning"))
                score -= 15

        return max(0.0, score)
