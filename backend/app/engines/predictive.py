"""
Predictive Maintenance Engine — per-server failure risk scoring (0-100, higher=worse).

Components scored: disk, psu, fan, memory, thermal.
Uses real signals where available (SMART flags, fan RPM, temps), falls back to
deterministic synthetic baselines where the BMC doesn't expose data.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


@dataclass
class RiskResult:
    overall_risk: float
    risk_level: str  # low | medium | high
    disk_risk: float = 0.0
    psu_risk: float = 0.0
    fan_risk: float = 0.0
    memory_risk: float = 0.0
    thermal_risk: float = 0.0
    factors: List[Dict[str, Any]] = field(default_factory=list)


def _level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


class PredictiveMaintenanceEngine:
    def calculate(self, server, snapshot, disks=None, dimms=None) -> RiskResult:
        factors: List[Dict[str, Any]] = []

        disk_risk = self._disk_risk(disks, snapshot, factors)
        psu_risk = self._psu_risk(snapshot, factors)
        fan_risk = self._fan_risk(snapshot, factors)
        memory_risk = self._memory_risk(dimms, snapshot, factors)
        thermal_risk = self._thermal_risk(snapshot, factors)

        # Overall = weighted max-leaning blend (worst component dominates)
        components = [disk_risk, psu_risk, fan_risk, memory_risk, thermal_risk]
        overall = round(0.55 * max(components) + 0.45 * (sum(components) / len(components)), 1)

        return RiskResult(
            overall_risk=overall, risk_level=_level(overall),
            disk_risk=round(disk_risk, 1), psu_risk=round(psu_risk, 1),
            fan_risk=round(fan_risk, 1), memory_risk=round(memory_risk, 1),
            thermal_risk=round(thermal_risk, 1), factors=factors,
        )

    def _age_years(self, server) -> Optional[float]:
        d = server.installation_date or server.procurement_date
        if not d:
            return None
        return (datetime.now(timezone.utc) - d).days / 365.0

    def _disk_risk(self, disks, snapshot, factors) -> float:
        risk = 8.0  # baseline
        if disks:
            for d in disks:
                if d.failure_predicted:
                    risk = max(risk, 90)
                    factors.append({"component": "disk", "reason": f"SMART failure predicted: {d.name}", "points": 90})
                if (d.read_errors or 0) + (d.write_errors or 0) > 0:
                    risk = max(risk, 55)
                    factors.append({"component": "disk", "reason": f"Read/write errors on {d.name}", "points": 55})
        if snapshot and snapshot.disk_usage_max_pct and snapshot.disk_usage_max_pct >= 90:
            risk = max(risk, 50)
            factors.append({"component": "disk", "reason": f"Disk {snapshot.disk_usage_max_pct:.0f}% full", "points": 50})
        return risk

    def _psu_risk(self, snapshot, factors) -> float:
        risk = 6.0
        if snapshot:
            if snapshot.psu_failed_count and snapshot.psu_failed_count > 0:
                risk = 85
                factors.append({"component": "psu", "reason": f"{snapshot.psu_failed_count} PSU failed", "points": 85})
            if snapshot.power_consumed_watts and snapshot.power_capacity_watts:
                ratio = snapshot.power_consumed_watts / snapshot.power_capacity_watts
                if ratio >= 0.9:
                    risk = max(risk, 45)
                    factors.append({"component": "psu", "reason": f"Power at {ratio*100:.0f}% capacity", "points": 45})
        return risk

    def _fan_risk(self, snapshot, factors) -> float:
        risk = 5.0
        if snapshot and snapshot.fan_failed_count and snapshot.fan_failed_count > 0:
            risk = 75 if snapshot.fan_failed_count > 1 else 50
            factors.append({"component": "fan", "reason": f"{snapshot.fan_failed_count} fan(s) failed", "points": int(risk)})
        return risk

    def _memory_risk(self, dimms, snapshot, factors) -> float:
        risk = 7.0
        if dimms:
            for d in dimms:
                if d.error_count and d.error_count > 0:
                    risk = max(risk, 60)
                    factors.append({"component": "memory", "reason": f"ECC errors on {d.slot_name}", "points": 60})
                if d.health and d.health.lower() not in ("ok", "unknown"):
                    risk = max(risk, 45)
                    factors.append({"component": "memory", "reason": f"DIMM {d.slot_name} {d.health}", "points": 45})
        return risk

    def _thermal_risk(self, snapshot, factors) -> float:
        risk = 5.0
        if snapshot and snapshot.cpu_temp_max:
            t = snapshot.cpu_temp_max
            if t >= 85:
                risk = 80
                factors.append({"component": "thermal", "reason": f"CPU {t:.0f}°C critical", "points": 80})
            elif t >= 75:
                risk = 45
                factors.append({"component": "thermal", "reason": f"CPU {t:.0f}°C elevated", "points": 45})
        return risk
