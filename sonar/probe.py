"""Network probes: ping (ICMP or TCP fallback), port scan, reverse DNS,
MAC address and vendor, NetBIOS name. Pure Python, no root required.

Ping methods, tried in this order when the method is "auto":
  icmp  unprivileged ICMP echo socket (needs net.ipv4.ping_group_range to
        include your group; Rocky sets 0-2147483647 by default)
  ping  /usr/bin/ping (setcap or the same sysctl)
  tcp   TCP connect to a few common ports; an accept *or* a refusal (RST)
        means the host is up
"""

from __future__ import annotations

import errno
import os
import random
import re
import select
import shutil
import socket
import struct
import subprocess
import threading
import time
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_PROBE_PORTS = [80, 443, 22, 445, 139, 3389, 8080, 53, 21, 23]
OUI_FILES = ["/usr/share/hwdata/oui.txt", "/usr/share/misc/oui.txt",
             "/usr/share/ieee-data/oui.txt"]


def raise_fd_limit() -> int:
    """Lift the soft open-files limit to the hard limit (no root needed)."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = hard if hard != resource.RLIM_INFINITY else 65536
        target = min(target, 65536)
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
        return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except Exception:
        return 1024


# --------------------------------------------------------------- ping

def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return ~s & 0xFFFF


def icmp_socket_allowed() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP)
        s.close()
        return True
    except OSError:
        return False


def icmp_ping(ip: str, timeout: float) -> Optional[float]:
    """One ICMP echo over an unprivileged datagram socket. Returns RTT in ms,
    None on timeout. Raises PermissionError if the socket isn't allowed."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP)
    try:
        seq = random.randint(1, 0xFFFF)
        payload = b"sonar-probe" + os.urandom(5)
        hdr = struct.pack("!BBHHH", 8, 0, 0, 0, seq)
        pkt = struct.pack("!BBHHH", 8, 0, _checksum(hdr + payload), 0, seq) + payload
        t0 = time.monotonic()
        s.sendto(pkt, (ip, 0))
        deadline = t0 + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            r, _, _ = select.select([s], [], [], left)
            if not r:
                return None
            data, addr = s.recvfrom(2048)
            if len(data) >= 8 and data[0] == 0 and addr[0] == ip:
                if struct.unpack("!H", data[6:8])[0] == seq:
                    return (time.monotonic() - t0) * 1000.0
    finally:
        s.close()


_PING_TIME = re.compile(r"time[=<]\s*([\d.]+)\s*ms")


def ping_binary(ip: str, timeout: float, ping_cmd: str = "ping") -> Optional[float]:
    """Run the system ping once. Returns RTT in ms or None."""
    exe = shutil.which(ping_cmd)
    if not exe:
        raise FileNotFoundError(ping_cmd)
    wait = max(1, int(round(timeout + 0.49)))
    try:
        p = subprocess.run([exe, "-n", "-c", "1", "-W", str(wait), ip],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=wait + 2, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"})
    except subprocess.TimeoutExpired:
        return None
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode == 0:
        m = _PING_TIME.search(out)
        return float(m.group(1)) if m else 0.0
    if p.returncode == 2 or "Operation not permitted" in p.stderr.decode("utf-8", "replace"):
        raise PermissionError(p.stderr.decode("utf-8", "replace").strip())
    return None


def _multi_connect(ip: str, ports: Iterable[int], timeout: float,
                   stop_on_first: bool = False,
                   stop: Optional[threading.Event] = None) -> Tuple[List[int], bool, Optional[float]]:
    """Non-blocking TCP connects to many ports at once.
    Returns (open_ports, any_response, first_response_ms). A refusal (RST)
    counts as a response, so it proves the host is up."""
    ports = list(ports)
    open_ports: List[int] = []
    responded = False
    first: Optional[float] = None
    batch = 32
    t0 = time.monotonic()
    for i in range(0, len(ports), batch):
        if stop is not None and stop.is_set():
            break
        socks: Dict[socket.socket, int] = {}
        for port in ports[i:i + batch]:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            rc = s.connect_ex((ip, port))
            if rc in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                socks[s] = port
            else:
                if rc == errno.ECONNREFUSED:
                    responded = True
                    first = first if first is not None else (time.monotonic() - t0) * 1000
                s.close()
        deadline = time.monotonic() + timeout
        try:
            while socks:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                _, w, _ = select.select([], list(socks), [], min(left, 0.2))
                for s in w:
                    port = socks.pop(s)
                    err = s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if err == 0:
                        open_ports.append(port)
                        responded = True
                    elif err == errno.ECONNREFUSED:
                        responded = True
                    if responded and first is None:
                        first = (time.monotonic() - t0) * 1000
                    s.close()
                if stop_on_first and responded:
                    break
                if stop is not None and stop.is_set():
                    break
        finally:
            for s in socks:
                s.close()
        if stop_on_first and responded:
            break
    return sorted(open_ports), responded, first


def tcp_ping(ip: str, timeout: float, ports: Optional[Iterable[int]] = None) -> Optional[float]:
    _, ok, first = _multi_connect(ip, ports or DEFAULT_PROBE_PORTS, timeout, stop_on_first=True)
    return first if ok else None


def scan_ports(ip: str, ports: Iterable[int], timeout: float,
               stop: Optional[threading.Event] = None) -> List[int]:
    return _multi_connect(ip, ports, timeout, stop=stop)[0]


class Pinger:
    """Chooses a ping method once and reuses it for every host."""

    def __init__(self, method: str = "auto", probe_ports: Optional[List[int]] = None):
        self.requested = method
        self.probe_ports = probe_ports or list(DEFAULT_PROBE_PORTS)
        self.method = self._choose(method)

    def _choose(self, method: str) -> str:
        if method in ("icmp", "ping", "tcp"):
            return method
        if icmp_socket_allowed():
            return "icmp"
        if shutil.which("ping"):
            try:
                ping_binary("127.0.0.1", 1.0)
                return "ping"
            except (PermissionError, FileNotFoundError, OSError):
                pass
        return "tcp"

    def ping(self, ip: str, timeout: float) -> Optional[float]:
        try:
            if self.method == "icmp":
                return icmp_ping(ip, timeout)
            if self.method == "ping":
                return ping_binary(ip, timeout)
        except (PermissionError, FileNotFoundError):
            self.method = "tcp"
        except OSError:
            return None
        return tcp_ping(ip, timeout, self.probe_ports)


# --------------------------------------------------------------- names

def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return ""


def read_neighbours(path: str = "/proc/net/arp") -> Dict[str, str]:
    """IP -> MAC from the kernel ARP table (complete entries only)."""
    table: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            next(fh, None)
            for line in fh:
                parts = line.split()
                if len(parts) >= 4 and parts[2] != "0x0" and parts[3] != "00:00:00:00:00:00":
                    table[parts[0]] = parts[3].upper()
    except OSError:
        pass
    return table


def local_interfaces() -> Dict[str, str]:
    """IP -> MAC for this computer's own IPv4 addresses (from `ip -o -4 addr`)."""
    out: Dict[str, str] = {}
    exe = shutil.which("ip")
    if not exe:
        return out
    try:
        txt = subprocess.run([exe, "-o", "-4", "addr", "show"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=5).stdout.decode()
    except (OSError, subprocess.TimeoutExpired):
        return out
    for line in txt.splitlines():
        m = re.match(r"\d+:\s+(\S+)\s+inet\s+([\d.]+)/", line)
        if not m:
            continue
        dev, ip = m.group(1).split("@")[0], m.group(2)
        try:
            with open("/sys/class/net/%s/address" % dev) as fh:
                mac = fh.read().strip().upper()
        except OSError:
            mac = ""
        if mac and mac != "00:00:00:00:00:00":
            out[ip] = mac
    return out


class OuiDb:
    """MAC vendor lookup from the IEEE OUI list shipped by hwdata."""

    def __init__(self, paths: Optional[List[str]] = None):
        self.paths = paths or OUI_FILES
        self._db: Optional[Dict[str, str]] = None
        self._lock = threading.Lock()
        self.source = ""

    def _load(self) -> Dict[str, str]:
        db: Dict[str, str] = {}
        pat = re.compile(r"^\s*([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})\s+\(hex\)\s+(.+?)\s*$")
        for path in self.paths:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        m = pat.match(line)
                        if m:
                            db["".join(m.group(1, 2, 3)).upper()] = m.group(4)
            except OSError:
                continue
            if db:
                self.source = path
                break
        return db

    def lookup(self, mac: str) -> str:
        if not mac:
            return ""
        with self._lock:
            if self._db is None:
                self._db = self._load()
        key = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()[:6]
        if len(key) < 6:
            return ""
        vendor = self._db.get(key, "")
        if not vendor and int(key[:2], 16) & 0x02:
            return "(locally administered)"
        return vendor

    def __len__(self):
        self.lookup("000000")
        return len(self._db or {})


# --------------------------------------------------------------- NetBIOS

def _nb_encode(name: bytes) -> bytes:
    name = name.ljust(16, b"\0")[:16]
    out = bytearray()
    for b in name:
        out.append(ord("A") + (b >> 4))
        out.append(ord("A") + (b & 0x0F))
    return bytes([32]) + bytes(out) + b"\0"


def nbstat_request(tid: int) -> bytes:
    """NBNS node status request for the wildcard name '*' (RFC 1002 4.2.17)."""
    return struct.pack("!HHHHHH", tid, 0x0000, 1, 0, 0, 0) + _nb_encode(b"*") + struct.pack("!HH", 0x21, 1)


def parse_nbstat(data: bytes) -> Dict[str, object]:
    """Parse a node status response -> {'name', 'group', 'mac', 'names'}."""
    if len(data) < 57:
        raise ValueError("short NBSTAT reply")
    off = 12
    # answer name: either a full encoded name or a compression pointer
    if data[off] & 0xC0 == 0xC0:
        off += 2
    else:
        while data[off] != 0:
            off += data[off] + 1
        off += 1
    rtype, _cls, _ttl, _rdlen = struct.unpack("!HHIH", data[off:off + 10])
    if rtype != 0x21:
        raise ValueError("not an NBSTAT reply")
    off += 10
    count = data[off]
    off += 1
    names = []
    for _ in range(count):
        raw = data[off:off + 15].decode("ascii", "replace").rstrip(" \0")
        suffix = data[off + 15]
        nflags = struct.unpack("!H", data[off + 16:off + 18])[0]
        names.append((raw, suffix, bool(nflags & 0x8000)))
        off += 18
    mac = ""
    if len(data) >= off + 6:
        mac = ":".join("%02X" % b for b in data[off:off + 6])
        if mac == "00:00:00:00:00:00":
            mac = ""
    name = next((n for n, s, g in names if s == 0x00 and not g), "")
    group = next((n for n, s, g in names if s == 0x00 and g), "")
    return {"name": name, "group": group, "mac": mac, "names": names}


def netbios_query(ip: str, timeout: float, port: int = 137) -> Dict[str, object]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(timeout)
        tid = random.randint(1, 0xFFFF)
        s.sendto(nbstat_request(tid), (ip, port))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = s.recvfrom(4096)
            except (socket.timeout, OSError):
                return {}
            if addr[0] == ip and len(data) >= 2 and struct.unpack("!H", data[:2])[0] == tid:
                try:
                    return parse_nbstat(data)
                except (ValueError, IndexError, struct.error):
                    return {}
        return {}
    finally:
        s.close()
