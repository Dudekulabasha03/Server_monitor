"""
Alert Engine — evaluates rules, deduplicates, routes notifications.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import structlog
from app.config import settings
from app.models.alerts import AlertSeverity, AlertCategory, AlertState

log = structlog.get_logger(__name__)


class AlertEngine:
    """
    Evaluates metric snapshots against alert rules.
    Sends notifications via configured channels.
    Handles deduplication (cooldown windows).
    """

    BUILTIN_RULES = [
        # Availability
        {
            "name": "server_offline",
            "title": "Server Offline / BMC Unreachable",
            "category": AlertCategory.AVAILABILITY,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: server.status and server.status.value == "offline",
            "message": lambda snap, server: f"{server.hostname} is offline or BMC unreachable.",
            "runbook": "Check power, network connectivity, and BMC status.",
        },
        # Thermal
        {
            "name": "cpu_temp_critical",
            "title": "CPU Temperature Critical",
            "category": AlertCategory.THERMAL,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.cpu_temp_max and snap.cpu_temp_max >= settings.TEMP_CPU_CRITICAL,
            "message": lambda snap, server: f"CPU max temperature {snap.cpu_temp_max:.1f}°C on {server.hostname} exceeds {settings.TEMP_CPU_CRITICAL}°C.",
            "runbook": "Verify airflow, check fan operation, clean air filters, rebalance workloads.",
            "metric_name": "cpu_temp_max",
            "threshold": settings.TEMP_CPU_CRITICAL,
        },
        {
            "name": "cpu_temp_warning",
            "title": "CPU Temperature Warning",
            "category": AlertCategory.THERMAL,
            "severity": AlertSeverity.WARNING,
            "check": lambda snap, server: snap and snap.cpu_temp_max and settings.TEMP_CPU_WARNING <= snap.cpu_temp_max < settings.TEMP_CPU_CRITICAL,
            "message": lambda snap, server: f"CPU max temperature {snap.cpu_temp_max:.1f}°C on {server.hostname} above warning threshold.",
            "metric_name": "cpu_temp_max",
            "threshold": settings.TEMP_CPU_WARNING,
        },
        # Inlet temperature
        {
            "name": "inlet_temp_critical",
            "title": "Inlet Temperature Critical",
            "category": AlertCategory.THERMAL,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.inlet_temp and snap.inlet_temp >= settings.TEMP_INLET_CRITICAL,
            "message": lambda snap, server: f"Inlet temperature {snap.inlet_temp:.1f}°C on {server.hostname} — datacenter cooling failure.",
            "runbook": "Check CRAC/CRAH units, airflow, and datacenter cooling systems immediately.",
            "metric_name": "inlet_temp",
            "threshold": settings.TEMP_INLET_CRITICAL,
        },
        {
            "name": "inlet_temp_warning",
            "title": "Inlet Temperature Warning",
            "category": AlertCategory.THERMAL,
            "severity": AlertSeverity.WARNING,
            "check": lambda snap, server: snap and snap.inlet_temp and settings.TEMP_INLET_WARNING <= snap.inlet_temp < settings.TEMP_INLET_CRITICAL,
            "message": lambda snap, server: f"Inlet temperature {snap.inlet_temp:.1f}°C on {server.hostname} above {settings.TEMP_INLET_WARNING}°C.",
            "metric_name": "inlet_temp",
            "threshold": settings.TEMP_INLET_WARNING,
        },
        # BMC sensor health aggregate
        {
            "name": "bmc_sensor_critical",
            "title": "BMC Sensor Critical",
            "category": AlertCategory.HARDWARE,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and getattr(snap, "sensor_health", None) == "Critical",
            "message": lambda snap, server: f"BMC reports Critical sensor state on {server.hostname}. Check thermal and power sensors.",
            "runbook": "Inspect BMC sensor readings via iDRAC/iLO/BMC web UI.",
        },
        {
            "name": "bmc_sensor_warning",
            "title": "BMC Sensor Warning",
            "category": AlertCategory.HARDWARE,
            "severity": AlertSeverity.WARNING,
            "check": lambda snap, server: snap and getattr(snap, "sensor_health", None) == "Warning",
            "message": lambda snap, server: f"BMC reports Warning sensor state on {server.hostname}.",
        },
        # Fan failures — single vs multiple
        {
            "name": "fan_failure_warning",
            "title": "Fan Failure — Cooling Redundancy Lost",
            "category": AlertCategory.HARDWARE,
            "severity": AlertSeverity.WARNING,
            "check": lambda snap, server: snap and snap.fan_failed_count and snap.fan_failed_count == 1,
            "message": lambda snap, server: f"1 fan failed on {server.hostname}. Monitor CPU temperatures closely.",
        },
        {
            "name": "fan_failure_critical",
            "title": "Fan Failures — Critical Cooling Risk",
            "category": AlertCategory.HARDWARE,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.fan_failed_count and snap.fan_failed_count >= 2,
            "message": lambda snap, server: f"{snap.fan_failed_count} fans failed on {server.hostname}. Thermal shutdown risk — immediate action required.",
            "runbook": "Shut down non-critical workloads immediately. Replace failed fans urgently.",
        },
        # Power / PSU — single vs multiple failures
        {
            "name": "psu_failure_warning",
            "title": "PSU Failure — Redundancy Lost",
            "category": AlertCategory.HARDWARE,
            "severity": AlertSeverity.WARNING,
            "check": lambda snap, server: snap and snap.psu_failed_count and snap.psu_failed_count == 1,
            "message": lambda snap, server: f"1 PSU failed on {server.hostname}. Redundancy lost — single PSU remaining. Replace urgently.",
        },
        {
            "name": "psu_failure_critical",
            "title": "PSU Failure — Multiple PSUs Failed",
            "category": AlertCategory.HARDWARE,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.psu_failed_count and snap.psu_failed_count >= 2,
            "message": lambda snap, server: f"{snap.psu_failed_count} PSUs failed on {server.hostname}. Server at risk of power loss. Immediate action required.",
            "runbook": "Evacuate workloads immediately. Replace failed PSUs or prepare for emergency shutdown.",
        },
        {
            "name": "power_headroom_critical",
            "title": "Power Capacity Critical",
            "category": AlertCategory.POWER,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: (
                snap and snap.power_consumed_watts and snap.power_capacity_watts
                and snap.power_consumed_watts / snap.power_capacity_watts >= 0.95
            ),
            "message": lambda snap, server: f"Power draw at {snap.power_consumed_watts / snap.power_capacity_watts * 100:.0f}% of PSU capacity on {server.hostname}.",
        },
        # Utilization
        {
            "name": "cpu_high_critical",
            "title": "CPU Utilization Critical",
            "category": AlertCategory.UTILIZATION,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.cpu_usage_avg and snap.cpu_usage_avg >= settings.CPU_USAGE_CRITICAL,
            "message": lambda snap, server: f"CPU utilization {snap.cpu_usage_avg:.0f}% on {server.hostname}.",
            "metric_name": "cpu_usage_avg",
            "threshold": settings.CPU_USAGE_CRITICAL,
        },
        {
            "name": "memory_high_critical",
            "title": "Memory Utilization Critical",
            "category": AlertCategory.UTILIZATION,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.memory_usage_pct and snap.memory_usage_pct >= settings.MEM_USAGE_CRITICAL,
            "message": lambda snap, server: f"Memory usage {snap.memory_usage_pct:.0f}% on {server.hostname}.",
            "metric_name": "memory_usage_pct",
            "threshold": settings.MEM_USAGE_CRITICAL,
        },
        {
            "name": "disk_usage_critical",
            "title": "Disk Usage Critical",
            "category": AlertCategory.STORAGE,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: snap and snap.disk_usage_max_pct and snap.disk_usage_max_pct >= settings.DISK_USAGE_CRITICAL,
            "message": lambda snap, server: f"Disk usage at {snap.disk_usage_max_pct:.0f}% on {server.hostname}.",
        },
        {
            "name": "disk_failure_predicted",
            "title": "Disk Failure Predicted (SMART)",
            "category": AlertCategory.STORAGE,
            "severity": AlertSeverity.CRITICAL,
            "check": lambda snap, server: False,  # Evaluated separately from disk objects
            "message": lambda snap, server: f"Disk failure predicted on {server.hostname}.",
        },
    ]

    def evaluate(self, server, snapshot, active_alert_names: set) -> List[Dict[str, Any]]:
        """
        Evaluate all rules against current state.
        Returns list of new alerts to fire (excluding already-active ones).
        """
        new_alerts = []
        for rule in self.BUILTIN_RULES:
            rule_name = rule["name"]
            try:
                should_fire = rule["check"](snapshot, server)
            except Exception as e:
                log.warning("alert_rule_eval_error", rule=rule_name, error=str(e))
                continue

            if should_fire and rule["title"] not in active_alert_names:
                try:
                    msg = rule["message"](snapshot, server)
                except Exception:
                    msg = rule["title"]

                new_alerts.append({
                    "id": str(uuid.uuid4()),
                    "server_id": server.id,
                    "severity": rule["severity"],
                    "category": rule["category"],
                    "title": rule["title"],
                    "message": msg,
                    "metric_name": rule.get("metric_name"),
                    "threshold_value": rule.get("threshold"),
                    "metric_value": self._get_metric_value(snapshot, rule.get("metric_name")),
                    "fired_at": datetime.now(timezone.utc),
                    "state": AlertState.FIRING,
                    "runbook_url": rule.get("runbook"),
                })

        return new_alerts

    def active_rule_titles(self, server, snapshot) -> set:
        """Return the set of rule titles whose condition currently holds true.

        Used to auto-resolve firing alerts whose condition has cleared.
        """
        titles = set()
        for rule in self.BUILTIN_RULES:
            try:
                if rule["check"](snapshot, server):
                    titles.add(rule["title"])
            except Exception:
                continue
        return titles

    @staticmethod
    def _get_metric_value(snapshot, metric_name: Optional[str]) -> Optional[float]:
        if not snapshot or not metric_name:
            return None
        return getattr(snapshot, metric_name, None)


class NotificationRouter:
    """Routes alerts to configured channels."""

    def __init__(self):
        self._email_sender = None
        self._teams_sender = None
        self._slack_sender = None

    async def notify(self, alert: Dict[str, Any], server) -> None:
        tasks = []

        if settings.SMTP_USER:
            tasks.append(self._send_email(alert, server))
        if settings.TEAMS_WEBHOOK_URL:
            tasks.append(self._send_teams(alert, server))
        if settings.SLACK_BOT_TOKEN:
            tasks.append(self._send_slack(alert, server))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    log.error("notification_failed", error=str(r), alert_id=alert.get("id"))

    async def _send_email(self, alert: Dict[str, Any], server) -> None:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        severity_emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
            alert.get("severity", "").lower() if hasattr(alert.get("severity"), "lower") else str(alert.get("severity", "")).lower(), "⚪"
        )
        subject = f"{severity_emoji} [{alert['severity']}] {alert['title']} — {server.hostname}"
        body = f"""
Helios — AMD Fleet Intelligence Alert

Server:   {server.hostname} ({server.bmc_ip})
Location: {server.datacenter} / Rack {server.rack} / U{server.rack_unit}
Severity: {alert['severity']}
Category: {alert['category']}

{alert['message']}

Metric:    {alert.get('metric_name', 'N/A')}
Value:     {alert.get('metric_value', 'N/A')}
Threshold: {alert.get('threshold_value', 'N/A')}

Fired At: {alert['fired_at']}

{f"Runbook: {alert['runbook_url']}" if alert.get('runbook_url') else ""}

---
Helios — AMD Fleet Intelligence
        """
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = settings.SMTP_USER
        msg.attach(MIMEText(body, "plain"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=False,
            start_tls=True,
        )

    async def _send_teams(self, alert: Dict[str, Any], server) -> None:
        import httpx
        color = {"critical": "FF0000", "warning": "FFA500", "info": "0078D4"}.get(
            str(alert.get("severity", "")).lower(), "808080"
        )
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": alert["title"],
            "sections": [{
                "activityTitle": f"🚨 {alert['title']}",
                "activitySubtitle": f"**{server.hostname}** — {server.datacenter}/Rack {server.rack}",
                "facts": [
                    {"name": "Severity", "value": str(alert["severity"])},
                    {"name": "Category", "value": str(alert["category"])},
                    {"name": "Message", "value": alert["message"]},
                    {"name": "Fired At", "value": str(alert["fired_at"])},
                ],
                "markdown": True,
            }],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(settings.TEAMS_WEBHOOK_URL, json=payload)

    async def _send_slack(self, alert: Dict[str, Any], server) -> None:
        from slack_sdk.web.async_client import AsyncWebClient
        emoji = {"critical": ":red_circle:", "warning": ":warning:", "info": ":information_source:"}.get(
            str(alert.get("severity", "")).lower(), ":white_circle:"
        )
        client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)
        await client.chat_postMessage(
            channel=settings.SLACK_CHANNEL,
            text=f"{emoji} *{alert['title']}* — `{server.hostname}`\n{alert['message']}",
        )
