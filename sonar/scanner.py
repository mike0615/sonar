"""Multithreaded scan engine (no Qt; the GUI wraps it in a QThread)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional

from . import probe


@dataclass
class ScanOptions:
    threads: int = 64
    timeout_ms: int = 1000
    ping_method: str = "auto"          # auto | icmp | ping | tcp
    probe_ports: List[int] = field(default_factory=lambda: list(probe.DEFAULT_PROBE_PORTS))
    resolve_hostnames: bool = True
    netbios: bool = True
    scan_ports: bool = True
    ports: List[int] = field(default_factory=lambda: [21, 22, 23, 80, 443, 445, 3389, 8080])
    show_dead: bool = False            # also report hosts that didn't answer


@dataclass
class HostResult:
    ip: str
    alive: bool = False
    rtt_ms: Optional[float] = None
    method: str = ""
    hostname: str = ""
    mac: str = ""
    vendor: str = ""
    netbios: str = ""
    workgroup: str = ""
    open_ports: List[int] = field(default_factory=list)
    scanned_at: str = ""

    def ports_text(self) -> str:
        return ",".join(str(p) for p in self.open_ports)

    def rtt_text(self) -> str:
        if self.rtt_ms is None:
            return ""
        return "<1 ms" if self.rtt_ms < 1 else "%d ms" % round(self.rtt_ms)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["open_ports"] = self.ports_text()
        d["rtt_ms"] = "" if self.rtt_ms is None else "%.1f" % self.rtt_ms
        return d


ResultCb = Callable[[HostResult], None]
ProgressCb = Callable[[int, int], None]


class Scanner:
    def __init__(self, options: ScanOptions, oui: Optional[probe.OuiDb] = None):
        self.opt = options
        self.stop_event = threading.Event()
        self.oui = oui or probe.OuiDb()
        self.pinger = probe.Pinger(options.ping_method, options.probe_ports)
        self.local = {}

    def stop(self):
        self.stop_event.set()

    def scan_host(self, ip: str) -> HostResult:
        timeout = max(0.05, self.opt.timeout_ms / 1000.0)
        r = HostResult(ip=ip, method=self.pinger.method,
                       scanned_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        rtt = self.pinger.ping(ip, timeout)
        if rtt is not None:
            r.alive, r.rtt_ms = True, rtt
        if not r.alive:
            return r
        if self.stop_event.is_set():
            return r
        if self.opt.resolve_hostnames:
            r.hostname = probe.reverse_dns(ip)
        r.mac = self.local.get(ip) or probe.read_neighbours().get(ip, "")
        if self.opt.netbios and not self.stop_event.is_set():
            nb = probe.netbios_query(ip, min(timeout, 1.0))
            r.netbios = str(nb.get("name", "") or "")
            r.workgroup = str(nb.get("group", "") or "")
            if not r.mac and nb.get("mac"):
                r.mac = str(nb["mac"])
        r.vendor = self.oui.lookup(r.mac)
        if self.opt.scan_ports and self.opt.ports and not self.stop_event.is_set():
            r.open_ports = probe.scan_ports(ip, self.opt.ports, timeout, self.stop_event)
        return r

    def run(self, addresses: List[str], on_result: ResultCb,
            on_progress: Optional[ProgressCb] = None) -> int:
        """Scan `addresses`; calls on_result for every live host (and dead
        ones when show_dead). Returns the number of live hosts."""
        probe.raise_fd_limit()
        self.local = probe.local_interfaces()
        total, done, alive = len(addresses), 0, 0
        workers = max(1, min(int(self.opt.threads), 512, total or 1))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sonar") as pool:
            pending = set()
            it = iter(addresses)
            # Feed the pool lazily so Stop takes effect quickly on big ranges.
            for ip in it:
                pending.add(pool.submit(self.scan_host, ip))
                if len(pending) >= workers * 2:
                    break
            while pending:
                fut = next(as_completed(pending))
                pending.discard(fut)
                done += 1
                try:
                    res = fut.result()
                except Exception:  # a probe bug must not kill the scan
                    res = None
                if res is not None and (res.alive or self.opt.show_dead):
                    alive += 1 if res.alive else 0
                    on_result(res)
                if on_progress:
                    on_progress(done, total)
                if not self.stop_event.is_set():
                    nxt = next(it, None)
                    if nxt is not None:
                        pending.add(pool.submit(self.scan_host, nxt))
        return alive
