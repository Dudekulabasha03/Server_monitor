"""
Resource Optimization Engine — classify servers and detect waste.

Categories: active | idle | underutilized | overutilized
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class UtilClass:
    category: str          # active | idle | underutilized | overutilized
    reason: str


class ResourceOptimizer:
    # Thresholds
    IDLE_CPU = 5.0
    UNDER_CPU = 10.0
    UNDER_MEM = 20.0
    OVER_CPU = 85.0
    OVER_MEM = 90.0

    def classify(self, snapshot, has_active_users: bool) -> UtilClass:
        if not snapshot or snapshot.cpu_usage_avg is None:
            return UtilClass("unknown", "No OS-level utilization data (OS agent not enabled)")

        cpu = snapshot.cpu_usage_avg or 0
        mem = snapshot.memory_usage_pct or 0

        if cpu >= self.OVER_CPU or mem >= self.OVER_MEM:
            return UtilClass("overutilized", f"CPU {cpu:.0f}% / Mem {mem:.0f}% near capacity")
        if cpu < self.IDLE_CPU and not has_active_users:
            return UtilClass("idle", f"CPU {cpu:.0f}%, no active users")
        if cpu < self.UNDER_CPU and mem < self.UNDER_MEM:
            return UtilClass("underutilized", f"CPU {cpu:.0f}% / Mem {mem:.0f}% — low usage")
        return UtilClass("active", f"CPU {cpu:.0f}% / Mem {mem:.0f}%")

    def waste_watts(self, snapshot, util: UtilClass) -> float:
        """Estimate reclaimable power for idle/underutilized servers."""
        if util.category in ("idle", "underutilized") and snapshot and snapshot.power_consumed_watts:
            return snapshot.power_consumed_watts
        return 0.0
