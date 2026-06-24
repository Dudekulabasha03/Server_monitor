"""
Root Cause Analysis + Event Correlation Engine (rule-based).

Given an alert and the server's recent snapshot, return possible causes,
impact, and recommended actions. Correlates multi-signal patterns.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class RCAResult:
    possible_causes: List[str]
    impact: List[str]
    recommended_actions: List[str]
    correlated_signals: List[str]


# Keyed by alert category/metric → RCA template
_RCA_RULES: Dict[str, Dict[str, List[str]]] = {
    "thermal": {
        "causes": ["Fan degradation or failure", "Airflow blockage / clogged filters",
                   "High sustained workload", "Datacenter cooling / high inlet temp"],
        "impact": ["CPU performance throttling", "Accelerated component wear", "Risk of thermal shutdown"],
        "actions": ["Verify fan operation and RPM", "Inspect airflow and clean filters",
                    "Reduce or migrate workload", "Check rack/row cooling capacity"],
    },
    "hardware": {
        "causes": ["Component hardware fault", "Failed or absent PSU/fan", "Aging hardware near EOL"],
        "impact": ["Loss of redundancy", "Potential unplanned downtime"],
        "actions": ["Inspect failed component", "Schedule replacement during maintenance window",
                    "Verify spare inventory"],
    },
    "power": {
        "causes": ["PSU instability", "Workload spike", "Input voltage fluctuation"],
        "impact": ["Risk of power-capping or shutdown", "Reduced PSU lifespan"],
        "actions": ["Check PSU health and redundancy", "Review recent workload changes",
                    "Verify PDU / input power"],
    },
    "storage": {
        "causes": ["Disk wear / SMART degradation", "Capacity exhaustion", "RAID degradation"],
        "impact": ["Risk of data loss", "Write failures", "Degraded I/O performance"],
        "actions": ["Replace flagged disk", "Expand or archive storage", "Rebuild RAID array"],
    },
    "utilization": {
        "causes": ["Runaway process", "Insufficient capacity for workload", "Memory leak"],
        "impact": ["Application slowdown", "OOM risk", "SLA breach"],
        "actions": ["Identify top consuming process", "Scale or migrate workload", "Add resources"],
    },
    "availability": {
        "causes": ["Network/BMC connectivity loss", "Power outage", "OS hang or crash"],
        "impact": ["Service outage", "Monitoring blind spot"],
        "actions": ["Check power and network", "Verify BMC reachability", "Console / power-cycle if needed"],
    },
}


class RCAEngine:
    def analyze(self, alert, snapshot) -> RCAResult:
        category = alert.category.value if hasattr(alert.category, "value") else str(alert.category)
        rule = _RCA_RULES.get(category, {
            "causes": ["Undetermined — review telemetry"],
            "impact": ["Unknown"],
            "actions": ["Investigate server detail and recent events"],
        })

        correlated = self._correlate(snapshot)
        return RCAResult(
            possible_causes=rule.get("causes", []),
            impact=rule.get("impact", []),
            recommended_actions=rule.get("actions", []),
            correlated_signals=correlated,
        )

    def _correlate(self, snapshot) -> List[str]:
        """Detect multi-signal patterns indicating a compound root cause."""
        signals = []
        if not snapshot:
            return signals

        hot = snapshot.cpu_temp_max and snapshot.cpu_temp_max >= 80
        fan_issue = snapshot.fan_failed_count and snapshot.fan_failed_count > 0
        high_power = (snapshot.power_consumed_watts and snapshot.power_capacity_watts and
                      snapshot.power_consumed_watts / snapshot.power_capacity_watts >= 0.85)
        high_cpu = snapshot.cpu_usage_avg and snapshot.cpu_usage_avg >= 85

        if hot and fan_issue:
            signals.append("⚠ CPU temp high + fan failure → likely COOLING FAILURE")
        if hot and high_power and high_cpu:
            signals.append("⚠ High temp + high power + high CPU → sustained overload")
        if hot and not fan_issue and not high_cpu:
            signals.append("⚠ High temp without workload or fan cause → check datacenter cooling/airflow")
        return signals
