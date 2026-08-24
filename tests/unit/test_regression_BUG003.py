"""
Regression test for BUG-003: IPv6 anonymization bypass.

_anonymize_ip() used a heuristic that dropped empty IPv6 segments
(caused by :: compression). Addresses like 2001:db8::1 were returned
unmasked, violating GDPR anonymization requirements.
"""

import pytest

from reasoner.api.middleware import _anonymize_ip


@pytest.mark.parametrize(
    "ip,expected",
    [
        # Compressed forms that previously bypassed masking
        ("2001:db8::1", "2001:db8::"),
        ("::1", "::"),
        ("fe80::1%eth0", "fe80::"),
        # Full forms
        (
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "2001:db8:85a3::",
        ),
        (
            "fe80:0000:0000:0000:0202:b3ff:fe1e:8329",
            "fe80::",
        ),
    ],
)
def test_anonymize_ip_masks_ipv6_correctly(ip, expected):
    """
    The last 64 bits (interface identifier) must be zeroed for all
    valid IPv6 representations, including :: compressed forms.
    """
    result = _anonymize_ip(ip)
    assert result == expected


def test_anonymize_ip_preserves_ipv4():
    """IPv4 masking must continue to work as before."""
    assert _anonymize_ip("192.168.1.42") == "192.168.1.0"


def test_anonymize_ip_none():
    assert _anonymize_ip(None) is None


def test_anonymize_ip_empty():
    assert _anonymize_ip("") is None
