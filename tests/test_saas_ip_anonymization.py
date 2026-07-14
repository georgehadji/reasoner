"""Tests for IP anonymization in audit logs (SEC-018)."""

from __future__ import annotations

import pytest

from reasoner.api.middleware import _anonymize_ip


def test_anonymize_ipv4():
    """IPv4 last octet is masked."""
    assert _anonymize_ip("192.168.1.42") == "192.168.1.0"


def test_anonymize_ipv4_short():
    """IPv4 with fewer than 4 parts is returned as-is."""
    assert _anonymize_ip("192.168.1") == "192.168.1"


def test_anonymize_ipv6():
    """IPv6 last 64 bits are masked."""
    assert _anonymize_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:db8:85a3::"


def test_anonymize_ipv6_short():
    """Compressed IPv6 (::) is correctly parsed and masked."""
    assert _anonymize_ip("::1") == "::"


def test_anonymize_none():
    """None input returns None."""
    assert _anonymize_ip(None) is None


def test_anonymize_empty():
    """Empty string returns None."""
    assert _anonymize_ip("") is None
