"""
PRISM OS-Provisioning API client + lshw-tree parsers.

Auth = HTTPBasic + API-KEY header (verified). hardware_info() returns an
lshw-style hardware tree from which we extract OS IP, CPU, memory, disks, NICs.
"""
from typing import Any, Dict, List, Optional
import httpx
import structlog
from app.config import settings

log = structlog.get_logger(__name__)


class PrismClient:
    def __init__(self):
        self.base = settings.PRISM_URL.rstrip("/")
        self._auth = (settings.PRISM_USER, settings.PRISM_PASSWORD)
        self._headers = {"API-KEY": settings.PRISM_API_KEY, "Content-Type": "application/json"}

    async def hardware_info(self, sut_name: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base}/station/hardware_info/"
        try:
            async with httpx.AsyncClient(verify=False, timeout=40) as client:
                resp = await client.post(url, json={"sut_name": sut_name},
                                         auth=self._auth, headers=self._headers)
                if resp.status_code != 200:
                    log.debug("prism_hw_non200", sut=sut_name, code=resp.status_code)
                    return None
                data = resp.json()
                if isinstance(data, dict) and data.get("detail"):  # e.g. "SUT not found"
                    return None
                return data
        except Exception as e:
            log.warning("prism_hw_error", sut=sut_name, error=str(e))
            return None

    async def check_sut_user(self, sut_name: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base}/station/check_sut_user/"
        try:
            async with httpx.AsyncClient(verify=False, timeout=25) as client:
                resp = await client.post(url, json={"sut_name": sut_name},
                                         auth=self._auth, headers=self._headers)
                return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None


# ── lshw tree parsers ────────────────────────────────────────────────────────

def _iter_nodes(tree: Any):
    """Recursively yield every dict node in the lshw tree."""
    if isinstance(tree, dict):
        yield tree
        for v in tree.values():
            yield from _iter_nodes(v)
    elif isinstance(tree, list):
        for x in tree:
            yield from _iter_nodes(x)


def _size_bytes(node: Dict[str, Any]) -> int:
    sz = node.get("size")
    if isinstance(sz, dict):
        try:
            return int(sz.get("#text", 0))
        except (ValueError, TypeError):
            return 0
    if isinstance(sz, (int, str)):
        try:
            return int(sz)
        except (ValueError, TypeError):
            return 0
    return 0


def extract_os_ip(tree: Dict[str, Any]) -> Optional[str]:
    for node in _iter_nodes(tree):
        if node.get("@class") != "network":
            continue
        cfg = node.get("configuration", {})
        settings_list = cfg.get("setting", []) if isinstance(cfg, dict) else []
        if isinstance(settings_list, dict):
            settings_list = [settings_list]
        for s in settings_list:
            if isinstance(s, dict) and s.get("@id") in ("ip", "ipv4"):
                ip = s.get("@value")
                if ip and not ip.startswith("127.") and not ip.startswith("169.254"):
                    return ip
    return None


def _first_logical(node: Dict[str, Any]) -> Optional[str]:
    ln = node.get("logicalname")
    if isinstance(ln, list):
        return ln[0] if ln else None
    return ln


def _capacity_from_model(model: str) -> int:
    """Best-effort capacity (bytes) from a drive model string when size isn't reported.
    Samsung encodes capacity in the part code, e.g. MZWLO3T8=3.84TB, MZVL2512=512GB."""
    import re
    m = model.upper()
    if "VIRTUAL" in m:
        return 0
    # explicit "3.84TB" / "1.6TB" / "960GB" in the model string (Dell etc.)
    explicit = re.search(r"(\d+(?:\.\d+)?)\s*TB", m)
    if explicit:
        return int(float(explicit.group(1)) * 1_000_000_000_000)
    explicit_gb = re.search(r"(\d+(?:\.\d+)?)\s*GB", m)
    if explicit_gb:
        return int(float(explicit_gb.group(1)) * 1_000_000_000)
    # Samsung-style code: 3T8 (3.8TB), 1T9 (1.92TB)
    tb = re.search(r"(\d)T(\d)", m)
    if tb:
        return int(float(f"{tb.group(1)}.{tb.group(2)}") * 1_000_000_000_000)
    gb = re.search(r"(512|960|480|256|128|1024|2048|3840|1920|7680)", m)
    if gb:
        return int(gb.group(1)) * 1_000_000_000
    return 0


def extract_hardware(tree: Dict[str, Any]) -> Dict[str, Any]:
    cpu_models: List[str] = []
    mem_total = 0
    dimm_count = 0
    disks: List[Dict[str, Any]] = []
    nics: List[Dict[str, Any]] = []

    for node in _iter_nodes(tree):
        cls = node.get("@class")
        if cls == "processor":
            prod = node.get("product")
            if prod and "core" in str(prod).lower():
                cpu_models.append(str(prod))
        elif cls == "memory":
            nid = str(node.get("@id", ""))
            if nid.startswith("bank"):
                b = _size_bytes(node)
                if b > 0:
                    mem_total += b
                    dimm_count += 1
        elif cls == "storage" and node.get("product"):
            # A real drive: model on this node, byte-size on a child disk/volume namespace.
            # Skip bare controllers (e.g. "FCH SATA Controller" with no drive attached).
            if "controller" in str(node.get("product")).lower() and not node.get("logicalname"):
                continue
            prod = str(node.get("product"))
            ln = _first_logical(node)
            cap = _size_bytes(node)
            if not cap:
                # descend into children for the largest namespace/volume size
                child_sizes = [
                    _size_bytes(k) for k in _iter_nodes(node)
                    if k is not node and k.get("@class") in ("disk", "volume") and _size_bytes(k) > 0
                ]
                if child_sizes:
                    cap = max(child_sizes)
            if not cap:
                cap = _capacity_from_model(prod)  # last-resort from model string
            disks.append({
                "name": ln or node.get("@id"),
                "model": prod,
                "capacity_gb": round(cap / 1_000_000_000) if cap else None,  # vendor GB (decimal)
                "media_type": "NVMe" if "nvme" in str(node.get("@id", "")).lower() else "Disk",
                "serial_number": node.get("serial"),
            })
        elif cls == "network":
            prod = node.get("product")
            ln = _first_logical(node)
            speed = _size_bytes(node)  # capacity here is bit/s
            nics.append({
                "name": ln or node.get("@id"),
                "model": str(prod) if prod else None,
                "mac_address": node.get("serial"),
                "speed_gbps": int(speed / 1_000_000_000) if speed else None,
                "link_status": "Up" if node.get("@disabled") != "true" else "Down",
            })

    cpu_count = len(cpu_models)
    return {
        "cpu_model": cpu_models[0] if cpu_models else None,
        "cpu_count": cpu_count or None,
        "memory_gb": round(mem_total / (1024 ** 3)) if mem_total else None,
        "dimm_count": dimm_count or None,
        "disks": disks,
        "nics": nics,
    }
