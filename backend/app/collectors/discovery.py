"""
Fleet Auto-Discovery — scans IP ranges for Redfish and IPMI endpoints.
Identifies vendor, model, serial number automatically.
"""
import asyncio
import ipaddress
from typing import List, Optional, Dict, Any
import httpx
import structlog

log = structlog.get_logger(__name__)


class DiscoveredServer:
    def __init__(self, ip: str):
        self.ip = ip
        self.redfish_available = False
        self.ipmi_available = False
        self.vendor: Optional[str] = None
        self.model: Optional[str] = None
        self.serial_number: Optional[str] = None
        self.hostname: Optional[str] = None
        self.bmc_firmware: Optional[str] = None


async def probe_redfish(ip: str, timeout: int = 5) -> Optional[Dict[str, Any]]:
    """Try to reach Redfish root on a given IP."""
    for port in [443, 80, 8443]:
        scheme = "https" if port != 80 else "http"
        url = f"{scheme}://{ip}:{port}/redfish/v1/"
        try:
            async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if "RedfishVersion" in data:
                        return {"port": port, "scheme": scheme, "data": data}
        except Exception:
            continue
    return None


async def probe_ipmi(ip: str, timeout: int = 3) -> bool:
    """Check if IPMI port 623 is open."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 623),
            timeout=timeout,
        )
        writer.close()
        return True
    except Exception:
        return False


async def discover_server(ip: str) -> Optional[DiscoveredServer]:
    """Probe a single IP for server management interfaces."""
    redfish_result, ipmi_result = await asyncio.gather(
        probe_redfish(ip),
        probe_ipmi(ip),
        return_exceptions=True,
    )

    redfish_ok = isinstance(redfish_result, dict) and redfish_result is not None
    ipmi_ok = isinstance(ipmi_result, bool) and ipmi_result

    if not redfish_ok and not ipmi_ok:
        return None

    server = DiscoveredServer(ip)
    server.redfish_available = redfish_ok
    server.ipmi_available = ipmi_ok

    if redfish_ok and isinstance(redfish_result, dict):
        data = redfish_result.get("data", {})
        oem = data.get("Oem", {})
        if "Dell" in oem:
            server.vendor = "dell"
        elif "Hpe" in oem:
            server.vendor = "hpe"
        elif "Lenovo" in oem:
            server.vendor = "lenovo"
        elif "Supermicro" in oem:
            server.vendor = "supermicro"

    log.info("discovered_server", ip=ip, redfish=redfish_ok, ipmi=ipmi_ok, vendor=server.vendor)
    return server


async def scan_ip_range(cidr: str, max_concurrent: int = 100) -> List[DiscoveredServer]:
    """
    Scan an entire CIDR range for servers.
    Example: scan_ip_range("10.10.50.0/24")
    """
    network = ipaddress.ip_network(cidr, strict=False)
    ips = [str(ip) for ip in network.hosts()]

    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_probe(ip: str):
        async with semaphore:
            return await discover_server(ip)

    log.info("starting_discovery_scan", cidr=cidr, total_ips=len(ips))
    results = await asyncio.gather(*[bounded_probe(ip) for ip in ips], return_exceptions=True)

    discovered = [r for r in results if isinstance(r, DiscoveredServer) and r is not None]
    log.info("discovery_complete", cidr=cidr, found=len(discovered))
    return discovered
