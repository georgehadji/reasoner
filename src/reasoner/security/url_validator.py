"""SSRF-safe URL validation for scraper and image downloaders.

Blocks private IP ranges, metadata endpoints, and internal hostnames.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# CIDR blocks that are never safe for server-side fetching
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private
    ipaddress.ip_network("172.16.0.0/12"),    # Private
    ipaddress.ip_network("192.168.0.0/16"),   # Private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / metadata
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("192.0.0.0/24"),     # IETF Protocol Assignments
    ipaddress.ip_network("198.18.0.0/15"),    # Benchmarking
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
    ipaddress.ip_network("::ffff:127.0.0.0/104"),  # IPv4-mapped loopback
]

# Hostnames that are always blocked (case-insensitive)
_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
}


def _resolve_to_ips(hostname: str) -> list[str]:
    """Resolve a hostname to IPv4 and IPv6 addresses."""
    try:
        # getaddrinfo returns tuples of (family, type, proto, canonname, sockaddr)
        infos = socket.getaddrinfo(hostname, None)
        return [info[4][0] for info in infos]
    except socket.gaierror:
        return []


def _is_blocked_ip(ip_str: str) -> bool:
    """Check if an IP string falls into a blocked network."""
    try:
        addr = ipaddress.ip_address(ip_str)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                return True
        return False
    except ValueError:
        return False


def is_safe_url(url: str) -> bool:
    """Return True if *url* is safe for the server to fetch.

    Checks:
      1. Scheme must be http:// or https://
      2. Host must not be a blocked hostname (localhost, etc.)
      3. If host is an IP, it must not be in a blocked network.
      4. If host is a domain, all resolved IPs must not be in blocked networks.
    """
    if not isinstance(url, str):
        return False

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    host_lower = host.lower()
    if host_lower in _BLOCKED_HOSTNAMES:
        return False

    # If the host looks like an IP address, check it directly.
    try:
        ipaddress.ip_address(host)
        return not _is_blocked_ip(host)
    except ValueError:
        pass

    # Hostname — resolve and verify all IPs.
    ips = _resolve_to_ips(host)
    if not ips:
        # Cannot resolve — conservative default is to block.
        return False

    for ip in ips:
        if _is_blocked_ip(ip):
            return False

    return True
