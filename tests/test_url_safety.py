"""Server-side fetches cannot reach non-public addresses (SEC-3).

The scraper checked only the first URL, then followed redirects, so a public
page answering ``302 -> http://169.254.169.254/`` reached cloud metadata. The
blocklist also missed ``0.0.0.0``, ``::`` and mapped private ranges, and DNS
was resolved separately for the check and the connect.
See docs/plans/audit-remediation-2026-10-20.md, SEC-3.
"""

from __future__ import annotations

import socket

import httpx
import pytest

from reasoner.infrastructure import safe_fetch
from reasoner.security import url_validator
from reasoner.security.url_validator import (
    UnsafeURLError,
    is_public_address,
    is_safe_url,
    resolve_public_url,
)

# Every address the audit showed passing the old blocklist, plus the classics.
_NOT_PUBLIC = [
    "0.0.0.0", "::", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
    "64:ff9b::a9fe:a9fe", "2002:a9fe:a9fe::1", "2001:0:4136:e378:8000:63bf:3fff:fdd2",
    "127.0.0.1", "127.1.2.3", "::1", "::ffff:7f00:1", "10.0.0.1", "172.16.5.4",
    "192.168.1.1", "169.254.169.254", "100.64.0.1", "fd00::1", "fe80::1",
    "224.0.1.1", "198.18.0.1", "not-an-ip",
]
_PUBLIC = ["8.8.8.8", "1.1.1.1", "2606:4700::1111", "::ffff:8.8.8.8", "64:ff9b::808:808"]


@pytest.mark.parametrize("ip", _NOT_PUBLIC)
def test_non_public_addresses_are_refused(ip):
    assert is_public_address(ip) is False


@pytest.mark.parametrize("ip", _PUBLIC)
def test_public_addresses_are_allowed(ip):
    assert is_public_address(ip) is True


@pytest.mark.parametrize("url", ["http://0.0.0.0:8003/", "http://[::]/", "http://[::ffff:169.254.169.254]/"])
def test_is_safe_url_refuses_audit_bypasses(url):
    assert is_safe_url(url) is False


@pytest.mark.asyncio
async def test_resolve_pins_the_checked_ip(monkeypatch):
    async def getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(url_validator, "_getaddrinfo", getaddrinfo)
    pinned = await resolve_public_url("https://example.com:8443/a?b=1")
    assert pinned.url == "https://93.184.216.34:8443/a?b=1"
    assert pinned.host == "example.com:8443"
    assert pinned.sni == "example.com"


@pytest.mark.asyncio
async def test_any_private_answer_refuses_the_host(monkeypatch):
    """A rebinding host may answer public and private; one private answer is enough."""
    async def getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80)) for ip in ("93.184.216.34", "127.0.0.1")]

    monkeypatch.setattr(url_validator, "_getaddrinfo", getaddrinfo)
    with pytest.raises(UnsafeURLError):
        await resolve_public_url("http://rebind.example/")


# ── safe_get ─────────────────────────────────────────────────────────────────


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve the test hostnames to fixed IPs."""
    table = {"public.example": "93.184.216.34", "other.example": "93.184.216.35"}

    async def getaddrinfo(host, port):
        if host not in table:
            raise socket.gaierror(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], port or 80))]

    monkeypatch.setattr(url_validator, "_getaddrinfo", getaddrinfo)


@pytest.mark.asyncio
async def test_redirect_to_metadata_is_refused(public_dns):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    async with _client(handler) as client:
        with pytest.raises(UnsafeURLError):
            await safe_fetch.safe_get(client, "http://public.example/r", max_bytes=1000)
    assert seen == ["http://93.184.216.34/r"], "the metadata address must never be requested"


@pytest.mark.asyncio
async def test_public_redirect_is_followed_with_host_header(public_dns):
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.headers["host"])
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "http://other.example/end"})
        return httpx.Response(200, text="hello")

    async with _client(handler) as client:
        response, body = await safe_fetch.safe_get(client, "http://public.example/start", max_bytes=1000)
    assert body == b"hello"
    assert hosts == ["public.example", "other.example"]


@pytest.mark.asyncio
async def test_too_many_redirects_is_refused(public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    async with _client(handler) as client:
        with pytest.raises(UnsafeURLError):
            await safe_fetch.safe_get(client, "http://public.example/", max_bytes=1000, max_redirects=2)


@pytest.mark.asyncio
async def test_body_is_capped(public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"A" * 10_000)

    async with _client(handler) as client:
        _, body = await safe_fetch.safe_get(client, "http://public.example/", max_bytes=100)
    assert body == b"A" * 100
