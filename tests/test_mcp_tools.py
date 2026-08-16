"""MCP server contract and behaviour tests.

Exercises the FastMCP server through a real in-memory client session
(mcp.shared.memory.create_connected_server_and_client_session) rather than
calling server.call_tool() directly -- the latter skips the request/session
layer FastMCP tools depend on for Context.request_context, so it cannot
exercise auth, quota, credits, or progress reporting, all of which read
that context.

Skipped entirely if the optional `mcp` extra is not installed -- this is the
one test module allowed to depend on it.
"""

from __future__ import annotations

import pytest

mcp_sdk = pytest.importorskip("mcp", reason="mcp extra not installed")

from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from reasoner.api.mcp import build_mcp_server  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

EXPECTED_TOOLS = {
    "reasoner_run",
    "reasoner_followup",
    "reasoner_gate",
    "reasoner_estimate",
    "reasoner_presets",
    "reasoner_health",
}

# Substrings that would signal an admin/key-management/billing-management
# tool leaking onto the MCP surface. None of these ever belong here.
FORBIDDEN_NAME_SUBSTRINGS = ("admin", "key", "delete", "gdpr", "billing", "revoke")


@pytest.fixture
def mcp_server():
    return build_mcp_server()


DONE_FRAME = 'data: {"type": "done", "total_cost_usd": 0.0191, "errors": []}\n\n'
SYNTHESIS_FRAME = (
    'data: {"type": "phase_complete", "phase": 5, "name": "Synthesis", '
    '"data": {"core_solution": "Migrate incrementally, starting with billing.", '
    '"critical_insights": ["The deploy pipeline is the real bottleneck."]}}\n\n'
)
PHASE_START_FRAME = 'data: {"type": "phase_start", "phase": 2, "name": "Generation"}\n\n'


def _patch_billable_run(monkeypatch):
    """Stub every collaborator reasoner_run touches, short of the tool itself."""
    from reasoner.api import dependencies as deps
    from reasoner.api import run_observability
    from reasoner.application.services import idempotency as idem

    fake_user = type("FakeUser", (), {"id": "mcp-test-user"})()

    async def fake_resolve(token):
        return fake_user

    async def fake_check_quota(user):
        return None

    async def fake_require_credits(user):
        return user

    async def fake_register_run(client_run_id):
        return None

    settled: list[dict] = []

    async def fake_settle(self, **kwargs):
        settled.append(kwargs)

    async def fake_stream(
        req, request=None, user_id=None, preset_service=None, pipeline_service=None
    ):
        yield PHASE_START_FRAME
        yield SYNTHESIS_FRAME
        yield DONE_FRAME

    monkeypatch.setattr(deps, "_resolve_auth_token", fake_resolve)
    monkeypatch.setattr(deps, "check_quota", fake_check_quota)
    monkeypatch.setattr(deps, "require_credits", fake_require_credits)
    monkeypatch.setattr(idem, "register_run", fake_register_run)
    monkeypatch.setattr(run_observability.CreditSink, "settle", fake_settle)

    import reasoner.api.streaming as streaming_mod
    monkeypatch.setattr(streaming_mod, "run_stream_cached", fake_stream)

    monkeypatch.setenv("REASONER_API_KEY", "rsn_live_test0000000000000000000000000000")

    return settled


# ── Tool inventory: the "no admin surface" guardrail ─────────────────


async def test_tool_list_is_exactly_the_expected_set(mcp_server):
    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.list_tools()
    assert {t.name for t in result.tools} == EXPECTED_TOOLS


async def test_no_admin_or_key_management_tool_is_ever_registered(mcp_server):
    """The hard rule: nothing from /api/admin/*, key management, or GDPR
    reaches this surface. Checked by substring so a future addition named
    unexpectedly (not just the six above) still trips this.
    """
    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.list_tools()
    for tool in result.tools:
        lowered = tool.name.lower()
        for banned in FORBIDDEN_NAME_SUBSTRINGS:
            assert banned not in lowered, f"{tool.name!r} looks like an admin tool ({banned!r})"


async def test_read_only_tools_are_marked_and_run_tools_are_not(mcp_server):
    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.list_tools()
    by_name = {t.name: t for t in result.tools}

    for name in ("reasoner_gate", "reasoner_estimate", "reasoner_presets", "reasoner_health"):
        assert by_name[name].annotations is not None
        assert by_name[name].annotations.readOnlyHint is True

    for name in ("reasoner_run", "reasoner_followup"):
        annotations = by_name[name].annotations
        assert annotations is None or annotations.readOnlyHint is not True


# ── Auth ───────────────────────────────────────────────────────────


async def test_reasoner_run_without_credentials_errors_cleanly(mcp_server, monkeypatch):
    """No REASONER_API_KEY, no Authorization header (stdio transport, no
    request) -> a clean tool error naming the problem, not a stack trace.
    """
    monkeypatch.delenv("REASONER_API_KEY", raising=False)

    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool("reasoner_run", {"problem": "Should we migrate?"})

    assert result.isError is True
    text = result.content[0].text if result.content else ""
    assert "credentials" in text.lower()
    assert "Traceback" not in text


async def test_reasoner_run_with_invalid_key_errors_cleanly(mcp_server, monkeypatch):
    from reasoner.api import dependencies as deps

    monkeypatch.setenv("REASONER_API_KEY", "rsn_live_not_a_real_key")

    async def raise_invalid(token):
        raise deps.HTTPException(status_code=401, detail="Invalid or revoked API key")

    monkeypatch.setattr(deps, "_resolve_auth_token", raise_invalid)

    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool("reasoner_run", {"problem": "test"})

    assert result.isError is True
    text = result.content[0].text if result.content else ""
    assert "Traceback" not in text


# ── Read-only tools work end-to-end ───────────────────────────────


async def test_reasoner_presets_returns_the_real_catalogue(mcp_server):
    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool("reasoner_presets", {})

    assert result.isError is not True
    payload = result.structuredContent or {}
    assert "presets" in payload
    assert len(payload["presets"]) > 0


async def test_reasoner_health_returns_a_status(mcp_server):
    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool("reasoner_health", {})

    assert result.isError is not True
    payload = result.structuredContent or {}
    assert payload.get("status") in ("healthy", "degraded", "unhealthy")


# ── The core guarantee: an MCP run is billed exactly like an HTTP run ──


async def test_reasoner_run_settles_credits_exactly_once(mcp_server, monkeypatch):
    settled = _patch_billable_run(monkeypatch)

    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool(
            "reasoner_run", {"problem": "Should we migrate off our monolith?"}
        )

    assert result.isError is not True
    assert len(settled) == 1
    assert settled[0]["cost_usd"] == 0.0191
    assert settled[0]["user_id"] == "mcp-test-user"

    payload = result.structuredContent or {}
    assert payload.get("synthesis") == "Migrate incrementally, starting with billing."
    assert payload.get("critical_insights") == ["The deploy pipeline is the real bottleneck."]


async def test_reasoner_run_reports_progress_per_phase(mcp_server, monkeypatch):
    _patch_billable_run(monkeypatch)
    progress_calls: list[tuple] = []

    async def on_progress(progress, total, message):
        progress_calls.append((progress, total, message))

    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool(
            "reasoner_run",
            {"problem": "Should we migrate?"},
            progress_callback=on_progress,
        )

    assert result.isError is not True
    # PHASE_START_FRAME and SYNTHESIS_FRAME are both phase_start/phase_complete;
    # the done frame is not, so exactly two progress notifications fire.
    assert len(progress_calls) == 2
    assert progress_calls[0][2] == "Generation"
    assert progress_calls[1][2] == "Synthesis"


async def test_reasoner_run_is_idempotent_on_client_run_id(mcp_server, monkeypatch):
    """A duplicate client_run_id must not silently double-run; register_run
    (mocked here to raise, matching the real store's contract) surfaces as a
    clean tool error rather than a second billed run.
    """
    _patch_billable_run(monkeypatch)

    from reasoner.application.services import idempotency as idem

    async def raise_duplicate(client_run_id):
        raise idem.RunAlreadyInProgressError(client_run_id)

    monkeypatch.setattr(idem, "register_run", raise_duplicate)

    async with create_connected_server_and_client_session(mcp_server) as session:
        result = await session.call_tool(
            "reasoner_run", {"problem": "test", "client_run_id": "dup-1"}
        )

    assert result.isError is True
    text = result.content[0].text if result.content else ""
    assert "dup-1" in text
