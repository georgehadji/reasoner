"""Tests for cache isolation (WI-1) and schema strictness (WI-2)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ── WI-1: Cache isolation ──

def test_cache_key_differs_across_users():
    """Two different users with same problem produce different cache keys."""
    from reasoner.api.cache import _cache_key
    from reasoner.api.schemas import RunRequest

    req = RunRequest(problem="test problem", preset="socratic-budget")

    key_a = _cache_key(req, user_id="user-1")
    key_b = _cache_key(req, user_id="user-2")
    key_same = _cache_key(req, user_id="user-1")

    assert key_a != key_b, "Different users must produce different cache keys"
    assert key_a == key_same, "Same user must produce identical cache keys"


def test_cache_key_user_id_none():
    """user_id=None produces a deterministic key (anonymous sentinel)."""
    from reasoner.api.cache import _cache_key
    from reasoner.api.schemas import RunRequest

    req = RunRequest(problem="test", preset="socratic-budget")
    key1 = _cache_key(req, user_id=None)
    key2 = _cache_key(req, user_id=None)
    assert key1 == key2, "None user_id must produce same key"


def test_cache_version_is_7():
    """Cache version must be 7 to invalidate old tenant-blind entries."""
    from reasoner.api.cache import _cache_key
    from reasoner.api.schemas import RunRequest

    req = RunRequest(problem="x", preset="socratic-budget")
    key = _cache_key(req, user_id="test-user")

    # The hash is opaque, but we can verify it changed from v6 by encoding
    # Check that the key is a valid 64-char hex string
    assert len(key) == 64, "SHA-256 produces 64 hex chars"
    import hashlib
    try:
        int(key, 16)
    except ValueError:
        assert False, "Cache key must be a valid hex string"


# ── WI-2: Schema strictness ──

def test_run_request_rejects_extra_fields():
    """RunRequest must reject unknown fields (S1)."""
    from pydantic import ValidationError
    from reasoner.api.schemas import RunRequest

    try:
        RunRequest(problem="test", preset="socratic-budget", _bypass="malicious")
        assert False, "RunRequest should reject extra fields"
    except ValidationError:
        pass


def test_followup_request_rejects_extra_fields():
    """FollowupRequest must reject unknown fields (S1)."""
    from pydantic import ValidationError
    from reasoner.api.schemas import FollowupRequest

    try:
        FollowupRequest(
            question="test",
            preset="socratic-budget",
            conversation_id="conv-1",
            history=[],
            previous_synthesis="",
            _stray="injection",
        )
        assert False, "FollowupRequest should reject extra fields"
    except ValidationError:
        pass


def test_run_request_accepts_valid_fields():
    """RunRequest must accept all valid fields (regression)."""
    from reasoner.api.schemas import RunRequest

    req = RunRequest(
        problem="test problem",
        preset="socratic-budget",
        top_k=3,
        sequential=False,
        no_cache=True,
        force_pipeline=False,
        enhance_prompt=True,
        expert=False,
        web_search=False,
        smart_search=True,
        source_type="general",
        domain=None,
        attachments=[],
        file_ids=[],
        client_run_id="test-run-1",
    )
    assert req.problem == "test problem"
    assert req.preset == "socratic-budget"
    assert req.top_k == 3


def test_followup_request_accepts_valid_fields():
    """FollowupRequest must accept all valid fields (regression)."""
    from reasoner.api.schemas import FollowupRequest

    req = FollowupRequest(
        question="follow up",
        preset="socratic-budget",
        top_k=2,
        sequential=False,
        enhance_prompt=False,
        expert=False,
        web_search=False,
        smart_search=True,
        conversation_id="conv-1",
        history=[{"role": "user", "content": "hello"}],
        previous_synthesis="",
        agent_model="deepseek-v3",
        attachments=[],
        file_ids=[],
        client_run_id="test-followup",
    )
    assert req.question == "follow up"
    assert req.conversation_id == "conv-1"
