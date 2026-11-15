"""Parse IP range text into a list of IPv4 addresses.

Accepted forms (comma, semicolon, or whitespace separated):
  192.0.2.10                 single address
  192.0.2.0/24               CIDR (network and broadcast skipped for /0-/30)
  192.0.2.1-192.0.2.254      start-end
  192.0.2.1-254              start-last octet
  192.0.2.*                  wildcard octet (same as .0/24 minus .0 and .255)
"""

from __future__ import annotations

import ipaddress
import re
from typing import Iterable, List

MAX_HOSTS = 65536


class RangeError(ValueError):
    pass


def _addr(text: str) -> ipaddress.IPv4Address:
    try:
        return ipaddress.IPv4Address(text.strip())
    except ValueError:
        raise RangeError("Not an IPv4 address: %r" % text.strip())


def _one(token: str) -> Iterable[ipaddress.IPv4Address]:
    token = token.strip()
    if not token:
        return []
    if "*" in token:
        parts = token.split(".")
        if len(parts) != 4 or parts[3] != "*" or "*" in "".join(parts[:3]):
            raise RangeError("Only the last octet can be a wildcard: %r" % token)
        token = ".".join(parts[:3]) + ".0/24"
    if "/" in token:
        try:
            net = ipaddress.IPv4Network(token, strict=False)
        except ValueError as e:
            raise RangeError("Bad CIDR %r: %s" % (token, e))
        if net.num_addresses > MAX_HOSTS:
            raise RangeError("%s has %d addresses; the limit is %d" % (token, net.num_addresses, MAX_HOSTS))
        return list(net.hosts()) if net.prefixlen < 31 else list(net)
    if "-" in token:
        start_s, end_s = token.split("-", 1)
        start = _addr(start_s)
        end_s = end_s.strip()
        if re.fullmatch(r"\d{1,3}", end_s):
            end = _addr(".".join(str(start).split(".")[:3] + [end_s]))
        else:
            end = _addr(end_s)
        if int(end) < int(start):
            raise RangeError("Range end is before its start: %r" % token)
        count = int(end) - int(start) + 1
        if count > MAX_HOSTS:
            raise RangeError("%r has %d addresses; the limit is %d" % (token, count, MAX_HOSTS))
        return [ipaddress.IPv4Address(i) for i in range(int(start), int(end) + 1)]
    return [_addr(token)]


def parse_range(text: str) -> List[str]:
    """Return the addresses in `text` in order, without duplicates."""
    seen = set()
    out: List[str] = []
    for token in re.split(r"[,;\s]+", text.strip()):
        for a in _one(token):
            s = str(a)
            if s not in seen:
                seen.add(s)
                out.append(s)
                if len(out) > MAX_HOSTS:
                    raise RangeError("More than %d addresses in total" % MAX_HOSTS)
    if not out:
        raise RangeError("Enter an IP address, a range (a.b.c.1-254) or a CIDR (a.b.c.0/24)")
    return out


def parse_ports(text: str) -> List[int]:
    """'22,80,443,8000-8010' -> sorted unique port numbers."""
    ports = set()
    for token in re.split(r"[,;\s]+", (text or "").strip()):
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            lo, hi = int(a), int(b)
            if lo > hi:
                lo, hi = hi, lo
            ports.update(range(lo, hi + 1))
        else:
            ports.add(int(token))
    bad = [p for p in ports if not 1 <= p <= 65535]
    if bad:
        raise RangeError("Port out of range: %d" % bad[0])
    if len(ports) > 4096:
        raise RangeError("At most 4096 ports per scan")
    return sorted(ports)
