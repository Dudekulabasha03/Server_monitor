"""
PIPT dashboard API client — BMC telemetry for the fleet via one fast call.

GET /fleet returns per-host: watts, cpu_watts, fan_rpm_max, hottest_c,
total_sel/new_critical_sel, power_state, status, bucket (idle/active).
No SSH / routing needed — covers hosts unreachable for OS SSH.
"""
from typing import Any, Dict, List, Optional
import httpx
import structlog
from app.config import settings

log = structlog.get_logger(__name__)


class PiptClient:
    def __init__(self):
        self.base = settings.PIPT_URL.rstrip("/")

    async def fleet(self) -> List[Dict[str, Any]]:
        """Return the per-host list from /fleet (empty list on failure)."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                resp = await client.get(f"{self.base}/fleet")
                if resp.status_code != 200:
                    log.warning("pipt_fleet_non200", code=resp.status_code)
                    return []
                data = resp.json()
                return data.get("hosts", []) if isinstance(data, dict) else []
        except Exception as e:
            log.warning("pipt_fleet_error", error=str(e))
            return []

    async def availability(self, window_hours: int = 6) -> Dict[str, Any]:
        """Return /availability (per-host bucket/score/schedulable/blocked_by)."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                resp = await client.get(f"{self.base}/availability", params={"window_hours": window_hours})
                return resp.json() if resp.status_code == 200 else {}
        except Exception as e:
            log.warning("pipt_availability_error", error=str(e))
            return {}

    async def host(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(verify=False, timeout=20) as client:
                resp = await client.get(f"{self.base}/host/{name}")
                return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None


def normalize_host(h: str) -> str:
    """Strip domain + lowercase so PIPT host matches Helios hostname."""
    return (h or "").split(".")[0].strip().lower()
