"""Key formats the redactor did not recognise (PR #105 follow-up).

xAI, Groq, Tavily, GitHub, Hugging Face and AWS credentials reached logs
verbatim: none had a prefix rule, and the generic `api_key=` rule only fires
when the variable name sits next to the value.

Fake keys are assembled at runtime so no key-shaped literal sits in the
source for secret scanners or push protection to flag.
"""

from __future__ import annotations

import time

import pytest

from reasoner.core.logging_utils import redact_sensitive

BODY = "FAKE0123" * 5  # 40 alphanumeric characters


def _key(*parts: str) -> str:
    return "".join(parts)


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        (_key("xai", "-", BODY), "xai-***REDACTED***"),
        (_key("gsk", "_", BODY), "gsk_***REDACTED***"),
        (_key("hf", "_", BODY), "hf_***REDACTED***"),
        (_key("gh", "p_", BODY[:36]), "ghp_***REDACTED***"),
        (_key("gh", "o_", BODY[:36]), "gho_***REDACTED***"),
        (_key("gh", "s_", BODY[:36]), "ghs_***REDACTED***"),
        (_key("github", "_pat_", "11ABCDEFG0", "_", BODY), "github_pat_***REDACTED***"),
        (_key("tvly", "-", BODY[:32]), "tvly-***REDACTED***"),
        (_key("tvly", "-dev-", BODY[:32]), "tvly-***REDACTED***"),
        (_key("AK", "IA", "FAKE0123FAKE4567"), "AKIA***REDACTED***"),
        (_key("AS", "IA", "FAKE0123FAKE4567"), "ASIA***REDACTED***"),
    ],
    ids=["xai", "groq", "hf", "ghp", "gho", "ghs", "github_pat", "tvly", "tvly-dev",
         "akia", "asia"],
)
def test_prefixed_key_is_redacted(key, replacement):
    out = redact_sensitive(f"provider rejected key {key} with 401")
    assert key not in out
    assert out == f"provider rejected key {replacement} with 401"
    # At offset 0 the boundary lookbehind reaches before the string start;
    # it must still count as a boundary.
    assert redact_sensitive(key) == replacement


@pytest.mark.parametrize(
    "assignment",
    [
        "aws_secret_access_key=",
        "AWS_SECRET_ACCESS_KEY: ",
        '"aws_session_token": "',
    ],
)
def test_aws_secret_with_slash_and_plus_is_redacted_whole(assignment):
    # AWS secrets contain `/` and `+`; the generic rule's class stops at both,
    # which used to redact the head and log the tail.
    secret = _key("wJalrXUtnFEMI", "/K7MDENG/", "bPxRfiCY+", "FAKEFAKEKEY")
    out = redact_sensitive(f"config {assignment}{secret}")
    assert "FAKEFAKEKEY" not in out
    assert "bPxRfiCY" not in out
    assert "***REDACTED***" in out


@pytest.mark.parametrize(
    "text",
    [
        # The xAI direct-adapter slug, and a lowercased model slug
        "routing via xAI-direct",
        "model xai-grok-4-fast-reasoning",
        # snake_case identifiers that share a prefix
        "calling hf_hub_download for the tokenizer",
        "gsk_config_loader failed",
        "ghp_token_env is unset",
        # too short to be a key
        "tvly-abc rejected",
        # AKIA inside a longer uppercase run, and mid-word
        "id AKIAFAKE0123FAKE4567EXTRA",
        "XAKIAFAKE0123FAKE4567",
    ],
)
def test_lookalikes_are_untouched(text):
    assert redact_sensitive(text) == text


# Same budget as test_security_review_round2: linear patterns stay far under it.
BUDGET_SECONDS = 2.0
N = 200_000


@pytest.mark.parametrize(
    "prefix",
    ["xai-", "gsk_", "hf_", "ghp_", "github_pat_", "tvly-", "AKIA", "A", "aws_session_token=",
     "AWS_SESSION_TOKEN="],
)
def test_prefix_runs_are_linear(prefix):
    text = prefix * (N // len(prefix))
    start = time.perf_counter()
    redact_sensitive(text)
    elapsed = time.perf_counter() - start
    assert elapsed < BUDGET_SECONDS, f"{prefix!r}: {elapsed:.1f}s for {len(text)} chars"
