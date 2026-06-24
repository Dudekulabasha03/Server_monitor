"""
Celery worker + beat schedule for collection orchestration.
"""
import asyncio
from celery import Celery
from celery.schedules import crontab
import structlog

from app.config import settings

log = structlog.get_logger(__name__)

celery_app = Celery(
    "fleet_monitor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue="collectors",
    task_routes={
        "app.worker.collect_redfish_fleet": {"queue": "collectors"},
        "app.worker.collect_ipmi_fleet": {"queue": "collectors"},
        "app.worker.collect_os_fleet": {"queue": "collectors"},
        "app.worker.compute_health_scores": {"queue": "collectors"},
        "app.worker.compute_risk_recos": {"queue": "collectors"},
        "app.worker.enrich_prism": {"queue": "collectors"},
        "app.worker.collect_pipt": {"queue": "collectors"},
        "app.worker.prune_old_data": {"queue": "collectors"},
        "app.worker.run_discovery": {"queue": "discovery"},
        "app.worker.evaluate_alerts": {"queue": "alerts"},
        "app.worker.sel_triage": {"queue": "alerts"},
    },
)

# Periodic schedule (Celery Beat)
celery_app.conf.beat_schedule = {
    "collect-redfish": {
        "task": "app.worker.collect_redfish_fleet",
        "schedule": float(settings.COLLECT_INTERVAL_REDFISH),
    },
    "collect-ipmi": {
        "task": "app.worker.collect_ipmi_fleet",
        "schedule": float(settings.COLLECT_INTERVAL_IPMI),
    },
    "collect-os": {
        "task": "app.worker.collect_os_fleet",
        "schedule": float(settings.COLLECT_INTERVAL_OS_AGENT),
    },
    "compute-health": {
        "task": "app.worker.compute_health_scores",
        "schedule": float(settings.COLLECT_INTERVAL_HEALTH_SCORE),
    },
    "compute-risk": {
        "task": "app.worker.compute_risk_recos",
        "schedule": 300.0,  # every 5 minutes
    },
    "enrich-prism": {
        "task": "app.worker.enrich_prism",
        "schedule": 21600.0,  # every 6 hours (hardware rarely changes)
    },
    "collect-pipt": {
        "task": "app.worker.collect_pipt",
        "schedule": float(settings.PIPT_INTERVAL),
    },
    "prune-old-data": {
        "task": "app.worker.prune_old_data",
        "schedule": 1800.0,  # every 30 minutes — retention keeps tables small
    },
    "evaluate-alerts": {
        "task": "app.worker.evaluate_alerts",
        "schedule": float(settings.EVALUATE_ALERTS_INTERVAL),
    },
    "run-discovery": {
        "task": "app.worker.run_discovery",
        "schedule": float(settings.DISCOVERY_SCAN_INTERVAL),
    },
    "sel-triage": {
        "task": "app.worker.sel_triage",
        "schedule": float(settings.SEL_AUTOTRIAGE_INTERVAL),
    },
}


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(name="app.worker.collect_redfish_fleet")
def collect_redfish_fleet():
    """Poll all Redfish-enabled servers and persist metrics."""
    from app.tasks.collection import collect_redfish_all
    return _run_async(collect_redfish_all())


@celery_app.task(name="app.worker.collect_ipmi_fleet")
def collect_ipmi_fleet():
    """Poll all IPMI-enabled servers."""
    from app.tasks.collection import collect_ipmi_all
    return _run_async(collect_ipmi_all())


@celery_app.task(name="app.worker.collect_os_fleet")
def collect_os_fleet():
    """Collect OS metrics over SSH for os_agent-enabled servers."""
    from app.tasks.collection import collect_os_all
    return _run_async(collect_os_all())


@celery_app.task(name="app.worker.compute_health_scores")
def compute_health_scores():
    """Recompute health scores for all servers from latest snapshots."""
    from app.tasks.collection import compute_all_health_scores
    return _run_async(compute_all_health_scores())


@celery_app.task(name="app.worker.compute_risk_recos")
def compute_risk_recos():
    """Run predictive maintenance + recommendation engines."""
    from app.tasks.collection import compute_risk_and_recommendations
    return _run_async(compute_risk_and_recommendations())


@celery_app.task(name="app.worker.enrich_prism")
def enrich_prism():
    """Enrich servers with hardware + OS IP from PRISM."""
    from app.tasks.collection import enrich_from_prism
    return _run_async(enrich_from_prism())


@celery_app.task(name="app.worker.collect_pipt")
def collect_pipt():
    """Merge PIPT BMC telemetry into snapshots."""
    from app.tasks.collection import collect_pipt_all
    return _run_async(collect_pipt_all())


@celery_app.task(name="app.worker.prune_old_data")
def prune_old_data():
    """Retention: delete raw snapshots > retention window + bound history tables."""
    from app.tasks.collection import prune_snapshots
    return _run_async(prune_snapshots())


@celery_app.task(name="app.worker.evaluate_alerts")
def evaluate_alerts():
    """Evaluate alert rules against latest snapshots."""
    from app.tasks.collection import evaluate_all_alerts
    return _run_async(evaluate_all_alerts())


@celery_app.task(name="app.worker.run_discovery")
def run_discovery():
    """Auto-discovery scan (configured CIDR ranges)."""
    log.info("discovery_scan_triggered")
    return {"status": "discovery not configured — set DISCOVERY_CIDRS"}


@celery_app.task(name="app.worker.sel_triage")
def sel_triage():
    """Autonomous Tier-2 SEL triage (reversible actions only; honors shadow + kill switch)."""
    from app.tasks.collection import autonomous_sel_triage
    return _run_async(autonomous_sel_triage())
