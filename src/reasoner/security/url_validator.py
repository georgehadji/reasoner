"""SSRF-safe URL validation for scraper and image downloaders.

Only publicly routable addresses are allowed. ``is_public_address`` is the
single rule. ``resolve_public_url`` resolves once and returns the checked
address, so the caller connects to exactly the IP that was validated (see
``infrastructure/safe_fetch.py``). Resolving twice, once to check and once to
connect, lets a DNS-rebinding host pass the check and then connect to
loopback.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

# Hostnames that are always blocked (case-insensitive)
_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
}

# RFC 6052 NAT64 prefix: the low 32 bits carry an IPv4 address.
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class UnsafeURLError(ValueError):
    """The URL must not be fetched by the server."""


@dataclass(frozen=True, slots=True)
class PinnedURL:
    """A URL whose host has been resolved to one checked public address."""

    url: str  # the original URL with its host replaced by the checked IP
    host: str  # Host header value (original host[:port])
    sni: str  # hostname for TLS SNI and certificate verification


def is_public_address(ip: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether *ip* is a publicly routable unicast address.

    IPv6 forms that embed an IPv4 address (mapped, 6to4, NAT64) are judged by
    that IPv4 address, so ``::ffff:169.254.169.254`` and
    ``64:ff9b::a9fe:a9fe`` cannot reach the metadata service. Teredo is
    refused outright because its client address is obfuscated. ``is_global``
    replaces a hand-kept blocklist that missed ``0.0.0.0``, ``::`` and every
    mapped private range.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.teredo:
            return False
        if addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        elif addr.sixtofour:
            addr = addr.sixtofour
        elif addr in _NAT64:
            addr = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return addr.is_global and not addr.is_multicast


def _resolve_to_ips(hostname: str) -> list[str]:
    """Resolve a hostname to IPv4 and IPv6 addresses."""
    try:
        # getaddrinfo returns tuples of (family, type, proto, canonname, sockaddr)
        infos = socket.getaddrinfo(hostname, None)
        return [info[4][0] for info in infos]
    except socket.gaierror:
        return []


def _host_if_allowed(url: str) -> tuple[str, object] | None:
    """(hostname, parsed URL) when scheme and hostname are acceptable."""
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        return None
    host = parsed.hostname
    if not host or host.lower() in _BLOCKED_HOSTNAMES:
        return None
    return host, parsed


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def is_safe_url(url: str) -> bool:
    """Return True if *url* is safe for the server to fetch.

    For input validation only. It resolves DNS synchronously and the answer
    can change before a later connect, so fetch through
    ``infrastructure.safe_fetch.safe_get``, which pins the checked address.
    """
    allowed = _host_if_allowed(url)
    if allowed is None:
        return False
    host, _ = allowed
    ips = [host] if _is_ip_literal(host) else _resolve_to_ips(host)
    # An unresolvable host is blocked: the conservative default.
    return bool(ips) and all(is_public_address(ip) for ip in ips)


async def _getaddrinfo(host: str, port: int | None) -> list:
    """Non-blocking DNS: the loop's resolver runs off the event loop thread."""
    return await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)


async def resolve_public_url(url: str) -> PinnedURL:
    """Resolve *url* once, without blocking the event loop, and pin a checked IP.

    Raises:
        UnsafeURLError: bad scheme, blocked hostname, no address, or any
            resolved address that is not public.
    """
    allowed = _host_if_allowed(url)
    if allowed is None:
        raise UnsafeURLError(f"URL not allowed: {url}")
    host, parsed = allowed

    if _is_ip_literal(host):
        ips = [host]
    else:
        try:
            infos = await _getaddrinfo(host, parsed.port)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"Cannot resolve {host}") from exc
        ips = [info[4][0] for info in infos]

    # Every answer must be public, or one rotated answer could be private.
    if not ips or not all(is_public_address(ip) for ip in ips):
        raise UnsafeURLError(f"Host resolves to a non-public address: {host}")

    ip = ips[0]
    netloc = (f"[{ip}]" if ":" in ip else ip) + (f":{parsed.port}" if parsed.port else "")
    return PinnedURL(
        url=urlunparse(parsed._replace(netloc=netloc)),
        host=parsed.netloc.rsplit("@", 1)[-1],
        sni=host,
    )
