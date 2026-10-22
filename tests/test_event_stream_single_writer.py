"""A streamed run's history replays without a version clash (PER-2).

RunStream writes the run's stream at versions 1..n. Bus publishers
(EventEmissionService, the handler) stamped version=1 on every event, and
persist_all_events stored them in the same stream, so PipelineAggregate raised
"Event version 1 doesn't match expected version 2". GET /api/pipelines/{id}
returned 500 and resume was refused for every streamed run.
See docs/plans/audit-remediation-2026-10-20.md, PER-2.
"""

from __future__ import annotations

import pytest

from reasoner.application.event_bus import bus as bus_mod
from reasoner.core.aggregates.pipeline import PipelineAggregate
from reasoner.core.events.domain_events import PipelineEventType as T
from reasoner.core.events.domain_events import make_event
from reasoner.infrastructure.persistence.event_store import EventStore


@pytest.mark.asyncio
async def test_bus_events_stay_out_of_the_replayed_stream(tmp_path, monkeypatch):
    store = EventStore(tmp_path / "events.db")
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.event_store.get_event_store", lambda *a, **k: store
    )
    run = "run-1"

    # The bus publishes first: the handler's start event and an emitter event,
    # both stamped version=1 on the run's aggregate.
    await bus_mod.persist_all_events(make_event(T.PIPELINE_STARTED, aggregate_id=run, version=1,
                                                problem="p"))
    await bus_mod.persist_all_events(make_event(T.PHASE_STARTED, aggregate_id=run, version=1,
                                                phase_name="Synthesis"))
    # RunStream, the stream's one writer.
    await store.save_events([make_event(T.PIPELINE_STARTED, aggregate_id=run, version=1, problem="p")])
    await store.save_events([make_event(T.PHASE_COMPLETED, aggregate_id=run, version=2,
                                        phase_name="Synthesis")])
    await store.save_events([make_event(T.PIPELINE_COMPLETED, aggregate_id=run, version=3)])

    history = await store.get_events(run)
    assert [e.version for e in history] == [1, 2, 3]

    aggregate = PipelineAggregate(aggregate_id=run)
    aggregate.load_from_history(history)  # raised ValueError before
    assert aggregate.version == 3


@pytest.mark.asyncio
async def test_persisted_llm_events_carry_no_prompt_text(monkeypatch):
    """PER-3: every LLM call's prompts and response were persisted, often under
    aggregate "unknown", which erasure never reaches."""
    saved: list = []

    class _Store:
        async def save_events(self, events):
            saved.extend(events)

    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.event_store.get_event_store", lambda *a, **k: _Store()
    )
    event = make_event(T.LLM_GENERATION_COMPLETED, aggregate_id="unknown", version=1,
                       model_name="m", system_prompt="SYS SECRET", user_prompt="USER SECRET",
                       raw_response="ANSWER SECRET", prompt_tokens=10, cost=0.01)

    await bus_mod.persist_all_events(event)

    (stored,) = saved
    assert (stored.system_prompt, stored.user_prompt, stored.raw_response) == ("", "", "")
    assert stored.model_name == "m" and stored.prompt_tokens == 10 and stored.cost == 0.01
    assert event.user_prompt == "USER SECRET", "the live event is not modified"


@pytest.mark.asyncio
async def test_gdpr_erase_uses_the_configured_store(monkeypatch):
    """PER-3: the route built the SQLite EventStore directly, whatever the backend.
    The registry's `events` store reaches the store through get_event_store()."""
    from reasoner.api import user_data

    names = {s.name: s for s in user_data.user_data_stores()}
    configured = object()
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.event_store._event_store", configured
    )

    assert names["events"]._get_store() is configured


def test_a_registry_built_without_a_store_gets_it_later(monkeypatch):
    """PER-5: run_stream builds the registry bare; if that came first, the
    worker kept event_store=None for its lifetime."""
    from reasoner.application.handlers import handlers

    monkeypatch.setattr(handlers, "_handler_registry", None)
    bare = handlers.get_handler_registry(pipeline_executor=object())
    store = object()
    again = handlers.get_handler_registry(object(), store)

    assert again is bare
    assert bare.event_store is store
    assert bare.query_handlers["GetPipelineStatusQuery"].event_store is store
    assert bare.command_handlers["ResumePipelineCommand"].event_store is store
