"""
SSH OS Agent — agentless OS metric collection over SSH.

Collects CPU%, memory, disk, network, load, and logged-in users by running
lightweight read-only commands on the target OS. No software installed on targets.
"""
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import structlog

log = structlog.get_logger(__name__)


class OSMetrics:
    def __init__(self, server_id: str):
        self.server_id = server_id
        self.collected_at = datetime.now(timezone.utc)
        self.cpu_usage_pct: Optional[float] = None
        self.load_1m: Optional[float] = None
        self.load_5m: Optional[float] = None
        self.load_15m: Optional[float] = None
        self.memory_usage_pct: Optional[float] = None
        self.memory_used_gb: Optional[float] = None
        self.memory_free_gb: Optional[float] = None
        self.swap_usage_pct: Optional[float] = None
        self.disk_usage_avg_pct: Optional[float] = None
        self.disk_usage_max_pct: Optional[float] = None
        self.net_rx_mbps: Optional[float] = None
        self.net_tx_mbps: Optional[float] = None
        self.net_errors_total: Optional[int] = None
        self.net_drops_total: Optional[int] = None
        self.sessions: List[Dict[str, Any]] = []
        self.top_processes: List[Dict[str, Any]] = []
        self.error: Optional[str] = None


class OSAgentCollector:
    """Collects OS metrics from a single host over SSH using asyncssh."""

    def __init__(self, server_id: str, host: str, username: str, password: str,
                 port: int = 22, timeout: int = 6, port_check_timeout: int = 2):
        self.server_id = server_id
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        self.port_check_timeout = port_check_timeout

    async def _port_open(self) -> bool:
        """Fast TCP pre-check so unreachable subnets drop in ~2s instead of full SSH timeout."""
        try:
            fut = asyncio.open_connection(self.host, self.port)
            reader, writer = await asyncio.wait_for(fut, timeout=self.port_check_timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def collect(self) -> OSMetrics:
        m = OSMetrics(self.server_id)
        try:
            import asyncssh
        except ImportError:
            m.error = "asyncssh not installed"
            return m

        if not await self._port_open():
            m.error = "unreachable (port 22 closed/no route)"
            return m

        try:
            async with asyncssh.connect(
                self.host, port=self.port, username=self.username, password=self.password,
                known_hosts=None, connect_timeout=self.timeout,
            ) as conn:
                # CPU sample: read /proc/stat twice, 1s apart
                stat1 = (await conn.run("cat /proc/stat", timeout=self.timeout)).stdout
                await asyncio.sleep(1)
                results = await asyncio.gather(
                    conn.run("cat /proc/stat", timeout=self.timeout),
                    conn.run("cat /proc/loadavg", timeout=self.timeout),
                    conn.run("cat /proc/meminfo", timeout=self.timeout),
                    conn.run("df -P -B1 -x tmpfs -x devtmpfs", timeout=self.timeout),
                    conn.run("cat /proc/net/dev", timeout=self.timeout),
                    conn.run("who", timeout=self.timeout),
                    conn.run("ps -eo comm,%cpu,%mem --sort=-%cpu | head -6", timeout=self.timeout),
                    return_exceptions=True,
                )
                stat2 = results[0].stdout if not isinstance(results[0], Exception) else ""
                self._parse_cpu(stat1, stat2, m)
                if not isinstance(results[1], Exception):
                    self._parse_loadavg(results[1].stdout, m)
                if not isinstance(results[2], Exception):
                    self._parse_meminfo(results[2].stdout, m)
                if not isinstance(results[3], Exception):
                    self._parse_df(results[3].stdout, m)
                if not isinstance(results[5], Exception):
                    self._parse_who(results[5].stdout, m)
                if not isinstance(results[6], Exception):
                    self._parse_ps(results[6].stdout, m)
        except Exception as e:
            m.error = str(e)
            log.warning("os_agent_failed", host=self.host, error=str(e))
        return m

    @staticmethod
    def _cpu_idle_total(stat: str):
        for line in stat.splitlines():
            if line.startswith("cpu "):
                parts = [int(x) for x in line.split()[1:]]
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
                total = sum(parts)
                return idle, total
        return None, None

    def _parse_cpu(self, s1: str, s2: str, m: OSMetrics):
        i1, t1 = self._cpu_idle_total(s1)
        i2, t2 = self._cpu_idle_total(s2)
        if None in (i1, t1, i2, t2) or t2 == t1:
            return
        idle_delta = i2 - i1
        total_delta = t2 - t1
        m.cpu_usage_pct = round((1 - idle_delta / total_delta) * 100, 1)

    def _parse_loadavg(self, s: str, m: OSMetrics):
        parts = s.split()
        if len(parts) >= 3:
            m.load_1m, m.load_5m, m.load_15m = float(parts[0]), float(parts[1]), float(parts[2])

    def _parse_meminfo(self, s: str, m: OSMetrics):
        info = {}
        for line in s.splitlines():
            k, _, v = line.partition(":")
            info[k.strip()] = float(v.strip().split()[0]) if v.strip() else 0  # kB
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        if total:
            m.memory_usage_pct = round((1 - avail / total) * 100, 1)
            m.memory_used_gb = round((total - avail) / (1024 ** 2), 1)
            m.memory_free_gb = round(avail / (1024 ** 2), 1)
        swt = info.get("SwapTotal", 0)
        swf = info.get("SwapFree", 0)
        if swt:
            m.swap_usage_pct = round((1 - swf / swt) * 100, 1)

    def _parse_df(self, s: str, m: OSMetrics):
        usages = []
        for line in s.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                try:
                    usages.append(float(parts[4].rstrip("%")))
                except ValueError:
                    continue
        if usages:
            m.disk_usage_avg_pct = round(sum(usages) / len(usages), 1)
            m.disk_usage_max_pct = max(usages)

    def _parse_who(self, s: str, m: OSMetrics):
        for line in s.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                m.sessions.append({
                    "username": parts[0],
                    "terminal": parts[1],
                    "login_time": " ".join(parts[2:4]) if len(parts) >= 4 else "",
                    "source_ip": parts[-1].strip("()") if "(" in line else None,
                    "session_type": "ssh" if "pts" in parts[1] else "console",
                })

    def _parse_ps(self, s: str, m: OSMetrics):
        for line in s.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    m.top_processes.append({
                        "name": parts[0],
                        "cpu_pct": float(parts[1]),
                        "mem_pct": float(parts[2]),
                    })
                except ValueError:
                    continue


class OSAgentFleetCollector:
    """Runs OSAgentCollector across the fleet CONCURRENTLY with a semaphore.

    Mirrors FleetRedfishCollector. Fast-fails unreachable hosts via the TCP
    pre-check so a cycle finishes well within the 30s schedule even when most
    OS subnets are unroutable.
    """

    def __init__(self, username: str, password: str, max_concurrent: int = 50,
                 connect_timeout: int = 6, port_check_timeout: int = 2):
        self.username = username
        self.password = password
        self.connect_timeout = connect_timeout
        self.port_check_timeout = port_check_timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def _one(self, server_id: str, host: str) -> "OSMetrics":
        async with self.semaphore:
            agent = OSAgentCollector(
                server_id, host, self.username, self.password,
                timeout=self.connect_timeout, port_check_timeout=self.port_check_timeout,
            )
            return await agent.collect()

    async def collect_fleet(self, targets: List[tuple]) -> List["OSMetrics"]:
        """targets = [(server_id, host), ...] → list[OSMetrics] (order preserved)."""
        results = await asyncio.gather(
            *[self._one(sid, host) for sid, host in targets],
            return_exceptions=True,
        )
        out = []
        for (sid, _), r in zip(targets, results):
            if isinstance(r, OSMetrics):
                out.append(r)
            else:
                m = OSMetrics(sid)
                m.error = str(r) if r else "collect failed"
                out.append(m)
        return out
