"""
Recommendation Engine — emits actionable recommendations ONLY for real problems.

Each recommendation includes numbered remediation steps. Healthy servers get
no recommendation (empty = good).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class Reco:
    category: str
    severity: str
    title: str
    body: str
    rationale: str
    steps: List[str] = field(default_factory=list)


class RecommendationEngine:
    def generate(self, server, snapshot, risk, util, firmware) -> List[Reco]:
        recos: List[Reco] = []
        now = datetime.now(timezone.utc)
        host = server.hostname

        # ── Predictive maintenance (high risk) ──────────────────────────────
        if risk and risk.risk_level == "high":
            top = max(risk.factors, key=lambda f: f.get("points", 0)) if risk.factors else None
            comp = top["component"] if top else "component"
            recos.append(Reco(
                "maintenance", "critical",
                f"High failure risk on {host}",
                f"Predicted {comp} risk is {risk.overall_risk:.0f}/100. Schedule inspection/replacement.",
                top["reason"] if top else "Elevated composite risk score.",
                steps=[
                    f"Open the server detail page for {host} and review the {comp} risk breakdown.",
                    f"Inspect the {comp} hardware via Redfish/BMC event log for warnings or predictive-failure flags.",
                    "Order a replacement part if the component shows degradation.",
                    "Schedule a maintenance window and migrate workloads off the host.",
                    "Replace the component, then re-run collection to confirm risk drops.",
                ],
            ))

        # ── Resource optimization ───────────────────────────────────────────
        if util:
            if util.category == "idle":
                recos.append(Reco(
                    "optimization", "warning", f"Idle server: {host}",
                    "Consolidate workloads or power off to reclaim capacity and energy.",
                    util.reason,
                    steps=[
                        f"Confirm {host} has no scheduled tests/jobs (check Utilization history).",
                        "Notify the owning team that the host appears idle.",
                        "Migrate or consolidate any remaining workloads to an active host.",
                        "Power off via BMC, or mark the host as a reclaim candidate.",
                    ],
                ))
            elif util.category == "underutilized":
                recos.append(Reco(
                    "optimization", "info", f"Underutilized: {host}",
                    "Consolidate workloads or repurpose this hardware.",
                    util.reason,
                    steps=[
                        f"Review 7-day utilization for {host} to confirm sustained low usage.",
                        "Identify candidate workloads from over-utilized hosts to migrate here.",
                        "Rebalance, or flag the host for repurposing.",
                    ],
                ))
            elif util.category == "overutilized":
                recos.append(Reco(
                    "optimization", "warning", f"Overutilized: {host}",
                    "Add capacity or migrate/load-balance workloads.",
                    util.reason,
                    steps=[
                        f"Identify the top CPU/memory consumers on {host} (server detail → processes).",
                        "Migrate the heaviest workload to an idle/underutilized host.",
                        "If sustained, plan a hardware upgrade or add a node to the pool.",
                    ],
                ))

        # ── Firmware compliance ─────────────────────────────────────────────
        if firmware and not firmware.compliant:
            outdated = [i.component for i in firmware.items if not i.compliant]
            recos.append(Reco(
                "firmware", "warning", f"Firmware outdated: {host}",
                f"Update {', '.join(outdated)} to the approved baseline.",
                f"{firmware.outdated_count} component(s) below baseline.",
                steps=[
                    f"Review the Firmware tab for {host} to see current vs approved versions.",
                    f"Download approved firmware for: {', '.join(outdated)}.",
                    "Schedule a maintenance window (firmware updates often need a reboot).",
                    "Flash via BMC/Redfish, then reboot and re-collect to confirm compliance.",
                ],
            ))

        # ── Lifecycle ───────────────────────────────────────────────────────
        if server.warranty_expiry:
            days = (server.warranty_expiry - now).days
            if days < 0:
                recos.append(Reco(
                    "lifecycle", "warning", f"Warranty expired: {host}",
                    "Renew support contract or plan hardware replacement.",
                    f"Warranty expired {abs(days)} days ago.",
                    steps=[
                        "Contact the vendor/procurement to renew the support contract.",
                        "If renewal isn't viable, add the host to the hardware-refresh plan.",
                        "Update the warranty date in Lifecycle once renewed.",
                    ],
                ))
            elif days < 90:
                recos.append(Reco(
                    "lifecycle", "info", f"Warranty expiring soon: {host}",
                    "Renew support contract before expiry.",
                    f"Warranty expires in {days} days.",
                    steps=[
                        "Start the renewal process with vendor/procurement now.",
                        "Update the warranty date in Lifecycle once confirmed.",
                    ],
                ))
        if server.eos_date and (server.eos_date - now).days < 0:
            recos.append(Reco(
                "lifecycle", "critical", f"End of Support: {host}",
                "Replace or upgrade — running unsupported hardware.",
                "Past End of Support date.",
                steps=[
                    "Flag the host as out-of-support to stakeholders.",
                    "Plan migration of all workloads to supported hardware.",
                    "Decommission and replace the host.",
                ],
            ))

        # ── Thermal ─────────────────────────────────────────────────────────
        if snapshot and snapshot.cpu_temp_max and snapshot.cpu_temp_max >= 85:
            recos.append(Reco(
                "thermal", "critical", f"Thermal threshold exceeded: {host}",
                "CPU temperature is critical — act to avoid throttling/damage.",
                f"CPU max temp {snapshot.cpu_temp_max:.0f}°C (>= 85°C).",
                steps=[
                    f"Check fan status for {host} (Thermal tab / BMC) — replace any failed fan.",
                    "Verify airflow: clear obstructions, check rack blanking panels, clean filters.",
                    "Confirm inlet/ambient temperature is within range; check datacenter cooling.",
                    "Reduce or migrate workload to lower thermal load.",
                    "Re-check temperature after 10–15 min; escalate if still critical.",
                ],
            ))
        elif snapshot and snapshot.cpu_temp_max and snapshot.cpu_temp_max >= 75:
            recos.append(Reco(
                "thermal", "warning", f"Elevated temperature: {host}",
                "CPU temperature is above the warning threshold.",
                f"CPU max temp {snapshot.cpu_temp_max:.0f}°C (>= 75°C).",
                steps=[
                    f"Monitor {host} temperature trend on the Thermal tab.",
                    "Verify fans are spinning and airflow is unobstructed.",
                    "Plan workload rebalancing if the trend keeps rising.",
                ],
            ))

        # ── Fan / PSU failures ──────────────────────────────────────────────
        if snapshot and snapshot.fan_failed_count and snapshot.fan_failed_count > 0:
            recos.append(Reco(
                "maintenance", "critical", f"Fan failure: {host}",
                f"{snapshot.fan_failed_count} fan(s) failed — thermal risk.",
                "Failed fan detected via Redfish.",
                steps=[
                    f"Identify the failed fan slot on {host} via the BMC.",
                    "Order/obtain a replacement fan module.",
                    "Hot-swap the fan (most chassis support it) during a brief window.",
                    "Confirm fan health returns to OK after replacement.",
                ],
            ))
        if snapshot and snapshot.psu_failed_count and snapshot.psu_failed_count > 0:
            recos.append(Reco(
                "power", "critical", f"PSU failure: {host}",
                f"{snapshot.psu_failed_count} PSU(s) failed — redundancy lost.",
                "Failed PSU detected via Redfish.",
                steps=[
                    f"Verify which PSU failed on {host} (BMC power subsystem).",
                    "Check the power feed/PDU for that PSU before replacing.",
                    "Replace the PSU module (hot-swap where supported).",
                    "Confirm redundancy is restored.",
                ],
            ))

        return recos
