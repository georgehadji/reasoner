"""Regression tests: Phase 2 perspectives must actually reach PipelineState.

run_perspectives_phase() built a PhaseOutput delta and returned it, but every
executor calls the phase function and discards the return:

  - api/execution/pipeline.py:241  `await fn(state, _services)`   (SSE path)
  - application/flows/runner.py:94 `await asyncio.wait_for(fn(...))`
  - application/flows/services.py:60 `await step.fn(state, self)`

Only the DAG runner (flows/pipeline_flow.py:106) ever called apply_to(). So on
the SSE path — the one real /api/run traffic takes — state.candidates stayed
empty even though Phase 2 had spent tokens on every perspective. Phase 3 then
hit its `if not state.candidates: return` guard and skipped silently with 0
tokens, and the UI rendered "No content for this phase".

Every sibling phase (run_critique_phase, run_stress_test_phase) mutates state
directly; Phase 2 was the odd one out.
"""

import json
from types import SimpleNamespace

import pytest

from reasoner.domain.pipeline_state import PipelineState


class _FakeRouter:
    """Cross-bloc routing so the diversity warning path stays quiet."""

    def __init__(self):
        self.primary = SimpleNamespace(model="anthropic/claude-sonnet")
        self.routing_table = {
            "constructive": SimpleNamespace(model="anthropic/claude-sonnet"),
            "destructive": SimpleNamespace(model="deepseek/deepseek-v3.2"),
            "systemic": SimpleNamespace(model="mistralai/mistral-small"),
            "minimalist": SimpleNamespace(model="openai/gpt-4o"),
        }


class _FakeServices:
    def __init__(self, fail_roles: set[str] | None = None):
        self.router = _FakeRouter()
        self.fail_roles = fail_roles or set()
        self.roles_called: list[str] = []

    def log(self, *args, **kwargs) -> None:
        pass

    async def call_llm(self, role: str, **kwargs):
        self.roles_called.append(role)
        if role in self.fail_roles:
            raise RuntimeError(f"{role} provider exploded")
        payload = {
            "core_analysis": f"Analysis from {role}.",
            "key_insights": [f"{role} insight"],
        }
        return json.dumps(payload), {"model": "fake", "input_tokens": 10, "output_tokens": 20}


def _state() -> PipelineState:
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    return state


@pytest.mark.asyncio
async def test_perspectives_populate_state_candidates():
    """The whole point of Phase 2: its candidates must land on the state."""
    from reasoner.application.flows.perspective_phases import run_perspectives_phase

    state = _state()
    services = _FakeServices()

    await run_perspectives_phase(state, services)

    assert state.candidates, "Phase 2 produced candidates but none reached PipelineState"
    assert len(state.candidates) == len(services.roles_called)


@pytest.mark.asyncio
async def test_critique_runs_after_perspectives():
    """Phase 3 must not skip after a successful Phase 2.

    This is the user-visible bug: critique hit `if not state.candidates: return`
    and reported "No content for this phase" with 0 tokens.
    """
    from reasoner.application.flows.perspective_phases import (
        run_critique_phase,
        run_perspectives_phase,
    )

    state = _state()
    services = _FakeServices()

    await run_perspectives_phase(state, services)
    before = len(services.roles_called)
    await run_critique_phase(state, services)

    assert "scoring" in services.roles_called, "critique skipped — it saw no candidates"
    assert len(services.roles_called) > before


@pytest.mark.asyncio
async def test_failed_perspective_is_recorded_on_state_errors():
    """A perspective that raises must surface as a state error, not vanish."""
    from reasoner.application.flows.perspective_phases import run_perspectives_phase

    state = _state()
    services = _FakeServices(fail_roles={"destructive"})

    await run_perspectives_phase(state, services)

    assert any("destructive" in e for e in state.errors)
    # The surviving perspectives still count.
    assert state.candidates
