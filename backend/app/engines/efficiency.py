"""
Power Efficiency Engine — kWh, cost, carbon footprint, idle consumption.
"""
from dataclasses import dataclass


# Grid carbon intensity (kg CO2 per kWh). US avg ~0.37; configurable.
DEFAULT_CARBON_FACTOR = 0.37


@dataclass
class EfficiencyResult:
    total_watts: float
    monthly_kwh: float
    monthly_cost: float
    monthly_carbon_kg: float
    idle_watts: float
    peak_watts: float


class PowerEfficiency:
    def compute(self, total_watts: float, idle_watts: float = 0.0, peak_watts: float = 0.0,
                rate_per_kwh: float = 0.12, pue: float = 1.5,
                carbon_factor: float = DEFAULT_CARBON_FACTOR) -> EfficiencyResult:
        monthly_kwh = (total_watts / 1000) * 24 * 30 * pue
        return EfficiencyResult(
            total_watts=round(total_watts, 1),
            monthly_kwh=round(monthly_kwh, 1),
            monthly_cost=round(monthly_kwh * rate_per_kwh, 2),
            monthly_carbon_kg=round(monthly_kwh * carbon_factor, 1),
            idle_watts=round(idle_watts, 1),
            peak_watts=round(peak_watts, 1),
        )
