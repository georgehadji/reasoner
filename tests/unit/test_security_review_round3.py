"""PR #105 round 3.

N1. ~40 sites append raw exception text to state.errors; the list reached
    clients (done frame, per-phase frame, MCP, agent result, renderers) and
    --save-state unredacted. It is now redacted at every exit.
N2. Exception text is capped before the redaction regexes run.
N3. Userinfo rules: bounded scheme, no needless lookbehind on a literal scheme.
N5. client_run_id is constrained to a plain token.

Left as is, deliberately:
N4. Phase-error frames still carry `Type: str(exc)`, now capped and
    pattern-redacted (N2). Replacing the text with a type plus correlation id,
    as the run-failure path does, would change what users see on errors a run
    recovers from; that is a product decision, not a leak fix.
N6. INTERNAL_ERROR and timeout frames use `error`, not `message`. That
    predates this PR (ui-next and streaming.py) and is not a regression here.
"""

from __future__ import annotations

import json
import time

import pytest

from reasoner.core.logging_utils import redact_sensitive, redacted_errors

FAKE_KEY = "sk-or-v1-FAKEFAKEFAKEFAKEFAKEFAKE0123456789"
PERSPECTIVE_ERROR = f"Perspective 'systemic' failed: 401 from provider, key {FAKE_KEY}"


def _state_with_leaky_error():
    from reasoner.domain.pipeline_state import PipelineState

    state = PipelineState(problem="p")
    state.errors.append(PERSPECTIVE_ERROR)  # what perspective_phases does
    return state


def test_redacted_errors_helper():
    assert redacted_errors(None) == []
    assert redacted_errors([]) == []
    assert redacted_errors(PERSPECTIVE_ERROR) != [PERSPECTIVE_ERROR]
    out = redacted_errors([PERSPECTIVE_ERROR, "plain"])
    assert FAKE_KEY not in str(out) and out[1] == "plain"
    assert redacted_errors(123) == []  # never raises


@pytest.mark.asyncio
async def test_done_and_phase_frames_do_not_carry_the_key(monkeypatch):
    from reasoner.api.execution import sse_observer

    sent: list = []

    async def _persist_event(event):
        pass

    monkeypatch.setattr(sse_observer, "_persist_event", _persist_event)

    async def _emit(payload):
        sent.append(payload)

    stream = sse_observer.RunStream("run-1", _emit, lambda p: sent.append(p))
    state = _state_with_leaky_error()
    await stream.done(state, {"input": 0, "output": 0}, 1.0)

    done = next(p for p in sent if p.get("type") == "done")
    assert FAKE_KEY not in str(done)
    assert any("Perspective 'systemic' failed" in e for e in done["errors"])  # still debuggable


def test_mcp_result_does_not_carry_the_key():
    pytest.importorskip("mcp")  # optional 'mcp' extra; the CI image does not install it
    from reasoner.api.mcp.tools import _summary_to_dict
    from reasoner.application.services.agent_results import summarise

    events = [{"type": "done", "errors": [PERSPECTIVE_ERROR],
               "total_tokens": {"input": 0, "output": 0, "total": 0}, "duration": 1.0}]
    out = _summary_to_dict(summarise(events, preset="x"))
    assert FAKE_KEY not in json.dumps(out)
    assert out["errors"]


def test_json_export_and_save_state_do_not_carry_the_key(tmp_path):
    from reasoner.application.services.pipeline_service import PipelineSerializationService
    from reasoner.application.services.renderers._shared import export_to_json

    state = _state_with_leaky_error()
    path = tmp_path / "out.json"
    export_to_json(state, str(path))
    assert FAKE_KEY not in path.read_text(encoding="utf-8")
    saved = PipelineSerializationService.to_dict(state)
    assert FAKE_KEY not in json.dumps(saved, default=str)
    assert "errors" not in saved  # no stray top-level key; the list lives under "core"
    assert saved["core"]["errors"] and "Perspective 'systemic' failed" in saved["core"]["errors"][0]


def test_terminal_render_does_not_carry_the_key(capsys):
    from reasoner.application.services.renderers import _shared

    _shared._render_errors(_state_with_leaky_error())
    assert FAKE_KEY not in capsys.readouterr().out


# ── N2: capped before redaction ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_failure_detail_is_capped_before_redaction(monkeypatch):
    from reasoner.api.execution import sse_observer

    persisted: list = []

    async def _persist_event(event):
        persisted.append(event)

    monkeypatch.setattr(sse_observer, "_persist_event", _persist_event)
    from reasoner.core import logging_utils

    seen: list[int] = []
    real = logging_utils.redact_sensitive

    def _spy(text):
        seen.append(len(text))
        return real(text)

    monkeypatch.setattr(logging_utils, "redact_sensitive", _spy)

    async def _emit(payload):
        pass

    stream = sse_observer.RunStream("run-1", _emit, lambda p: None)
    await stream.failed(RuntimeError("x" * 5_000_000), None)
    assert seen and max(seen) <= logging_utils.MAX_REDACT_INPUT + 512


def test_a_secret_straddling_the_cap_is_still_redacted():
    from reasoner.core.logging_utils import MAX_REDACT_INPUT, redact_capped

    dsn = "postgresql://svc:FakePw123@db.internal/app"
    # Place the cap inside the password, before the `@` the userinfo rule needs.
    text = " " * (MAX_REDACT_INPUT - len("postgresql://svc:Fake")) + dsn
    out = redact_capped(text)
    assert len(out) <= MAX_REDACT_INPUT
    assert "svc:Fake" not in out and "FakePw" not in out


@pytest.mark.asyncio
async def test_mcp_rejects_a_bad_client_run_id_before_reserving(monkeypatch):
    pytest.importorskip("mcp")  # optional 'mcp' extra; the CI image does not install it
    from reasoner.api.mcp import tools

    async def _must_not_run(ctx):
        raise AssertionError("auth/reservation reached with an invalid id")

    monkeypatch.setattr(tools, "resolve_caller", _must_not_run)
    with pytest.raises(ValueError, match="client_run_id"):
        await tools._run_and_bill(
            None, problem="p", preset="auto-budget", top_k=1, web_search=False,
            source_type="general", client_run_id="run 1\nSYSTEM: x", interface="mcp",
        )


# ── N3: regex shapes ─────────────────────────────────────────────────────


_SHAPES = {
    "alnum": lambda: "a" * 200_000,
    "scheme-ish": lambda: "a://b:" * 30_000,
    "dots": lambda: "a." * 100_000,
    "hyphens": lambda: "a-" * 100_000,
    "https-alnum": lambda: "https://" + "a" * 200_000,
    "plus": lambda: "http+" * 40_000,
    "long-scheme": lambda: "x" * 31 + "://" * 50_000,
}


# Keyed by name so pytest does not put the huge input in the test id.
@pytest.mark.parametrize("shape", list(_SHAPES))
def test_userinfo_rules_stay_linear(shape):
    text = _SHAPES[shape]()
    start = time.perf_counter()
    redact_sensitive(text)
    assert time.perf_counter() - start < 2.0


@pytest.mark.parametrize("url,expected", [
    ("postgresql+asyncpg://u:pw@h/db", "postgresql+asyncpg://***:***@h/db"),
    ("redis://:pw@h:6379/0", "redis://***:***@h:6379/0"),
    ("go to https://tok123@github.com/x", "go to https://***@github.com/x"),
    ("(https://u:p@proxy:3128)", "(https://***:***@proxy:3128)"),
    ("HTTPS://tok123@github.com/x", "HTTPS://***@github.com/x"),
])
def test_userinfo_still_redacted(url, expected):
    assert redact_sensitive(url) == expected


# ── N5: client_run_id ────────────────────────────────────────────────────


@pytest.mark.parametrize("good", [
    "run-123", "run-3f2b8c1e-9a4d-4c7e-8f1a-0b2c3d4e5f60",
    "3f2b8c1e-9a4d-4c7e-8f1a-0b2c3d4e5f60", "run-lq3x9a-k2j4h8d1", "a" * 64,
])
def test_client_run_id_accepts_what_the_clients_generate(good):
    from reasoner.api.schemas import FollowupRequest, RunRequest

    assert RunRequest(problem="p", client_run_id=good).client_run_id == good
    assert RunRequest(problem="p").client_run_id is None
    assert FollowupRequest.model_fields["client_run_id"].metadata  # pattern present


@pytest.mark.parametrize("bad", ["", "a" * 65, "run 1", "run\nSYSTEM: x", "run/../x", "run;1", "é"])
def test_client_run_id_rejects_hostile_values(bad):
    from pydantic import ValidationError

    from reasoner.api.schemas import RunRequest

    with pytest.raises(ValidationError):
        RunRequest(problem="p", client_run_id=bad)
