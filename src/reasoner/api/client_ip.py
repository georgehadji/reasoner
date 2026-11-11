"""Trusted-proxy-aware client IP resolution.

Prevents X-Forwarded-For spoofing by only trusting IPs listed in
TRUSTED_PROXIES. If no trusted proxies are configured, falls back to
the direct connection IP.
"""

from __future__ import annotations

import ipaddress

from fastapi import Request

from reasoner.core.settings import settings


def get_client_ip(request: Request, trusted_proxies: list[str] | None = None) -> str:
    """Resolve the actual client IP from a request.

    Strategy:
    1. If no trusted proxies are configured, return the direct connection IP.
    2. If X-Forwarded-For is absent, return the direct connection IP.
    3. Parse the X-Forwarded-For chain (left = client, right = closest proxy).
    4. Walk from the rightmost IP toward the left, stopping at the first
       IP that is NOT in the trusted-proxies list. This is the client IP.
    5. If every IP in the chain is a trusted proxy, return the direct
       connection IP as a safe fallback.

    Args:
        request: The incoming FastAPI request.
        trusted_proxies: Optional override list. Defaults to settings.TRUSTED_PROXIES.

    Returns:
        The resolved client IP address string.
    """
    direct_ip = request.client.host if request.client else "127.0.0.1"
    proxies = trusted_proxies if trusted_proxies is not None else settings.TRUSTED_PROXIES

    # Only a trusted peer may speak for the client: anyone else can send any XFF.
    if not proxies or not ip_in_networks(direct_ip, proxies):
        return direct_ip

    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return direct_ip

    # Parse chain: client, proxy1, proxy2, ..., closest_proxy
    ips = [ip.strip() for ip in forwarded.split(",")]

    # Walk from rightmost (closest to server) to leftmost (original client)
    for ip in reversed(ips):
        if not ip_in_networks(ip, proxies):
            return ip

    # All IPs in the chain are trusted proxies — fallback to direct connection
    return direct_ip


def ip_in_networks(ip: str, entries) -> bool:
    """Whether ``ip`` equals or falls inside any entry (plain address or CIDR)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip in entries
    for entry in entries:
        try:
            if addr in ipaddress.ip_network(entry.strip(), strict=False):
                return True
        except ValueError:
            continue
    return False
