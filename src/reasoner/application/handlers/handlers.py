"""
Application Layer - Command and Query Handlers

Handlers process commands and queries, coordinating between
domain layer and infrastructure layer.
"""

from __future__ import annotations

import logging
import asyncio
import importlib
from typing import Any

from reasoner.application.commands import (
    RunPipelineCommand,
    ResumePipelineCommand,
    StopPipelineCommand,
    ExecuteWidgetCommand,
)
from reasoner.application.queries import (
    GetPipelineStatusQuery,
    GetHistoryQuery,
    ListPresetsQuery,
)
from reasoner.core.aggregates.pipeline import PipelineAggregate
from reasoner.core.events.domain_events import make_event, EventType
# get_event_bus imported lazily in constructors to avoid circular import with api/__init__.py

logger = logging.getLogger(__name__)


def _get_event_bus():
    """Lazy import to avoid circular dependency with api/__init__.py."""
    from reasoner.application.event_bus import get_event_bus
    return get_event_bus()


# ─────────────────────────────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────────────

from typing import Callable, Awaitable, Protocol

from reasoner.application.commands import RunPipelineCommand
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.pipeline_state import PipelineState


class PipelineExecutionPort(Protocol):
    """Interface for pipeline execution — application layer depends on this port,
    not on api-layer implementations. The api layer provides the concrete
    implementation (PipelineExecutionService from api/execution/pipeline.py).

    This inverts the dependency: handlers.py (application) defines the port;
    api/execution/pipeline.py (api) implements it.
    """

    async def execute_run(
        self,
        command: RunPipelineCommand,
        router: ProviderRouter,
        sse_emit: Callable[[dict | str], Awaitable[None]],
        user_id: str | None = None,
        initial_state: PipelineState | None = None,
    ) -> PipelineState:
        ...


class RunPipelineCommandHandler:
    """
    Handler for RunPipelineCommand.
    
    Orchestrates pipeline execution using new architecture.
    Accepts an optional PipelineExecutionPort for SSE streaming;
    falls back to direct pipeline.run() when not provided.
    """
    
    def __init__(
        self,
        llm_router: Any,
        event_store: Any | None = None,
        pipeline_executor: PipelineExecutionPort | None = None,
    ):
        self.llm_router = llm_router
        self.event_store = event_store
        self.event_bus = _get_event_bus()
        self._pipeline_executor = pipeline_executor
    
    async def handle(
        self,
        command: RunPipelineCommand,
        sse_emit: Callable[[dict], Awaitable[None]] | None = None,
        initial_state: PipelineState | None = None,
    ) -> PipelineAggregate:
        """Execute pipeline command, optionally emitting SSE events.

        initial_state carries follow-up continuity (conversation history,
        previous synthesis, turn number, persona agent_model override) —
        it must reach PipelineExecutionPort.execute_run()/ReasonerPipeline
        below, both of which already know how to consume it.
        """
        # Create aggregate
        aggregate = PipelineAggregate(aggregate_id=command.command_id)
        
        # Record pipeline started event
        start_event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id=command.command_id,
            version=1,
            problem=command.problem,
            preset=command.preset,
            method=command.method or "multi-perspective",
            options={
                "top_k": command.top_k,
                "source_type": command.source_type,
                "domain": command.domain,
                "parallel": command.parallel,
            },
        )
        aggregate.record_event(start_event)
        
        if sse_emit:
            await sse_emit({"type": "start"})

        # Persist event
        if self.event_store:
            await self.event_store.save_events([start_event])
        
        # Publish event
        await self.event_bus.publish(start_event)
        
        # Execute pipeline phases
        from reasoner.infrastructure.llm.router import ProviderRouter

        router = ProviderRouter(primary=self.llm_router)

        try:
            from reasoner.application.services.pipeline_service import PipelineService
            from reasoner.application.orchestrator import PipelineOrchestrator
            
            if sse_emit:
                if self._pipeline_executor:
                    state = await self._pipeline_executor.execute_run(
                        command, router, sse_emit,
                        user_id=getattr(command, "user_id", None),
                        initial_state=initial_state,
                    )
                else:
                    raise RuntimeError(
                        "SSE streaming requested but no PipelineExecutionPort injected"
                    )
            else:
                # Legacy non-streaming path (sse_emit=None): construct + run pipeline directly.
                from reasoner.pipeline import ReasonerPipeline
                pipeline = ReasonerPipeline(
                    router=router,
                    preset_name=command.preset,
                    top_k=command.top_k,
                    source_type=command.source_type,
                    domain=command.domain,
                    parallel_perspectives=command.parallel,
                    user_id=getattr(command, "user_id", None),
                    initial_state=initial_state,
                )
                state = await pipeline.run(problem=command.problem)
            
            # Record completion event
            completion_event = make_event(
                EventType.PIPELINE_COMPLETED,
                aggregate_id=command.command_id,
                version=aggregate.version + 1,
                solution={"core_solution": getattr(state.core, "final_solution", "") if hasattr(state, "core") else ""},
                total_tokens={"total": getattr(state.meta, "total_tokens", 0)} if hasattr(state, "meta") else {},
                total_duration_seconds=getattr(state.meta, "total_duration", 0) if hasattr(state, "meta") else 0,
                phases_completed=len(getattr(state.meta, "phase_results", []) if hasattr(state, "meta") else []),
            )
            aggregate.record_event(completion_event)
            
            if sse_emit:
                await sse_emit({"type": "end", "data": {"synthesis": {"core_solution": "Completed"}}})

            # Persist and publish
            if self.event_store:
                await self.event_store.save_events([completion_event])
            await self.event_bus.publish(completion_event)
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            if sse_emit:
                await sse_emit({"type": "error", "error": str(e)})
            
            # Record failure event
            failure_event = make_event(
                EventType.PIPELINE_FAILED,
                aggregate_id=command.command_id,
                version=aggregate.version + 1,
                error=str(e),
                phase_at_failure=aggregate.get_last_phase() or "",
                phases_completed=len(aggregate.state_data.phase_results) if hasattr(aggregate, "state_data") else 0,
            )
            aggregate.record_event(failure_event)
            
            if self.event_store:
                await self.event_store.save_events([failure_event])
            await self.event_bus.publish(failure_event)
            
            raise
        
        return aggregate


class ResumePipelineCommandHandler:
    """Handler for ResumePipelineCommand."""
    
    def __init__(self, event_store: Any, llm_router: Any):
        self.event_store = event_store
        self.llm_router = llm_router
        self.event_bus = _get_event_bus()
    
    async def handle(self, command: ResumePipelineCommand) -> dict[str, Any]:
        """Resume pipeline from event history.

        Reconstructs aggregate state from stored events and returns
        the current status. Full execution resumption requires the
        caller to re-submit a run request with the recovered context.
        """
        # Load event history
        history = await self.event_store.get_events(command.pipeline_id)
        if not history:
            raise ValueError(f"No pipeline found with ID: {command.pipeline_id}")

        # Rebuild aggregate
        aggregate = PipelineAggregate(aggregate_id=command.pipeline_id)
        aggregate.load_from_history(history)

        # Check if can resume
        if not aggregate.can_resume():
            raise ValueError(f"Pipeline {command.pipeline_id} cannot be resumed (status: {aggregate.state_data.status})")

        last_phase = aggregate.get_last_phase()
        synthesis_text = ""
        if aggregate.state_data.synthesis and isinstance(aggregate.state_data.synthesis, dict):
            synthesis_text = aggregate.state_data.synthesis.get("core_solution", "") or ""

        return {
            "pipeline_id": command.pipeline_id,
            "status": aggregate.state_data.status,
            "can_resume": True,
            "last_phase": last_phase,
            "phases_completed": [p["phase"] for p in aggregate.state_data.phase_results],
            "total_tokens": aggregate.state_data.total_tokens,
            "errors": aggregate.state_data.errors,
            "problem": aggregate.state_data.problem,
            "preset": aggregate.state_data.preset,
            "method": aggregate.state_data.method,
            "previous_synthesis": synthesis_text,
        }


class StopPipelineCommandHandler:
    """Handler for StopPipelineCommand."""
    
    def __init__(self, event_store: Any | None = None):
        self.event_store = event_store
        self.event_bus = _get_event_bus()
    
    async def handle(self, command: StopPipelineCommand) -> dict[str, Any]:
        """Stop running pipeline."""
        # Signal cancellation via the per-run RunStateStore that api.py
        # checks inside run_stream.
        import reasoner.api as api
        await api._run_store.request_cancel(command.pipeline_id)

        # Record stop event (if we have event store)
        if self.event_store:
            event = make_event(
                EventType.PHASE_FAILED,
                aggregate_id=command.pipeline_id,
                version=0,  # Will be set by aggregate
                phase_name="user_stopped",
                error=f"Stopped by user: {command.reason}",
            )
            await self.event_store.save_events([event])

        return {"status": "stopped", "pipeline_id": command.pipeline_id}


class ExecuteWidgetCommandHandler:
    """Handler for ExecuteWidgetCommand."""
    
    def __init__(self):
        from reasoner.infrastructure.widgets import get_widget_registry
        self.registry = get_widget_registry()
        self.event_bus = _get_event_bus()
    
    async def handle(self, command: ExecuteWidgetCommand) -> dict[str, Any]:
        """Execute widget."""
        if command.auto_detect:
            # Auto-detect widgets from query
            results = await self.registry.auto_execute(command.query)
            
            if results:
                return {
                    "detected": True,
                    "widgets": [r.to_dict() for r in results],
                }
            
            return {"detected": False, "widgets": []}
        else:
            # Execute specific widget
            result = await self.registry.execute_widget(
                command.widget_type,
                command.params,
            )
            
            # Publish event
            if result.success:
                event = make_event(
                    EventType.WIDGET_EXECUTED,
                    aggregate_id=command.command_id,
                    version=1,
                    widget_type=command.widget_type,
                    result=result.data,
                    duration_seconds=result.duration_seconds,
                )
            else:
                event = make_event(
                    EventType.WIDGET_FAILED,
                    aggregate_id=command.command_id,
                    version=1,
                    widget_type=command.widget_type,
                    error=result.error,
                )
            
            await self.event_bus.publish(event)
            
            return {
                "detected": True,
                "widgets": [result.to_dict()],
            }


# ─────────────────────────────────────────────────────────────────────
# QUERY HANDLERS
# ─────────────────────────────────────────────────────────────────────

class GetPipelineStatusQueryHandler:
    """Handler for GetPipelineStatusQuery."""
    
    def __init__(self, event_store: Any | None = None):
        self.event_store = event_store
    
    async def handle(self, query: GetPipelineStatusQuery) -> dict[str, Any]:
        """Get pipeline status."""
        if not self.event_store:
            return {"error": "Event store not available"}
        
        # Load events
        history = await self.event_store.get_events(query.pipeline_id)
        
        if not history:
            return {"error": "Pipeline not found"}
        
        # Rebuild aggregate
        aggregate = PipelineAggregate(aggregate_id=query.pipeline_id)
        aggregate.load_from_history(history)
        
        return {
            "pipeline_id": query.pipeline_id,
            "status": aggregate.state_data.status,
            "problem": aggregate.state_data.problem,
            "method": aggregate.state_data.method,
            "preset": aggregate.state_data.preset,
            "last_phase": aggregate.get_last_phase(),
            "phases_completed": len(aggregate.state_data.phase_results),
            "can_resume": aggregate.can_resume(),
        }


class GetHistoryQueryHandler:
    """Handler for GetHistoryQuery."""
    
    def __init__(self, event_store: Any | None = None):
        self.event_store = event_store
    
    async def handle(self, query: GetHistoryQuery) -> dict[str, Any]:
        """Get search history."""
        if not self.event_store:
            # Fallback to file-based history
            return self._get_file_history(query)
        
        # Get from event store
        pipelines = await self.event_store.list_pipelines(
            limit=query.limit,
            offset=query.offset,
        )
        
        return {
            "total": len(pipelines),
            "entries": [
                {
                    "id": p["aggregate_id"],
                    "problem": p.get("problem", ""),
                    "preset": p.get("preset", ""),
                    "method": p.get("method", ""),
                    "status": p.get("status", ""),
                    "timestamp": p.get("created_at", ""),
                }
                for p in pipelines
            ],
        }
    
    def _get_file_history(self, query: GetHistoryQuery) -> dict[str, Any]:
        """Fallback to file-based history."""
        import json
        from pathlib import Path
        
        history_dir = Path(__file__).parent.parent / "history"
        entries = []
        
        for f in history_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                entries.append(data)
            except Exception:
                pass
        
        entries = sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "total": len(entries),
            "entries": entries[query.offset:query.offset + query.limit],
        }


class ListPresetsQueryHandler:
    """Handler for ListPresetsQuery."""
    
    async def handle(self, query: ListPresetsQuery) -> dict[str, Any]:
        """List available presets."""
        from reasoner.presets import PRESETS, get_preset
        
        presets = []
        for name, config in PRESETS.items():
            if query.method and query.method not in name:
                continue
            
            presets.append({
                "name": name,
                "description": config.get("description", ""),
                "method": name.split("-")[0] if "-" in name else "multi-perspective",
                "tier": self._get_tier(name),
            })
        
        return {"presets": presets, "total": len(presets)}
    
    def _get_tier(self, preset_name: str) -> str:
        """Get preset tier from name."""
        if "budget" in preset_name:
            return "budget"
        elif "premium" in preset_name:
            return "premium"
        else:
            return "standard"


# ─────────────────────────────────────────────────────────────────────
# HANDLER REGISTRY
# ─────────────────────────────────────────────────────────────────────

class HandlerRegistry:
    """Central registry for all command and query handlers."""
    
    def __init__(
        self,
        llm_router: Any,
        event_store: Any | None = None,
        pipeline_executor: PipelineExecutionPort | None = None,
    ):
        self.llm_router = llm_router
        self.event_store = event_store
        
        # Initialize handlers
        self.command_handlers = {
            "RunPipelineCommand": RunPipelineCommandHandler(llm_router, event_store, pipeline_executor),
            "ResumePipelineCommand": ResumePipelineCommandHandler(event_store, llm_router),
            "StopPipelineCommand": StopPipelineCommandHandler(event_store),
            "ExecuteWidgetCommand": ExecuteWidgetCommandHandler(),
        }
        
        self.query_handlers = {
            "GetPipelineStatusQuery": GetPipelineStatusQueryHandler(event_store),
            "GetHistoryQuery": GetHistoryQueryHandler(event_store),
            "ListPresetsQuery": ListPresetsQueryHandler(),
        }
    
    async def handle_command(self, command: Any) -> Any:
        """Route command to appropriate handler."""
        command_name = command.__class__.__name__
        handler = self.command_handlers.get(command_name)
        
        if not handler:
            raise ValueError(f"No handler for command: {command_name}")
        
        return await handler.handle(command)
    
    async def handle_query(self, query: Any) -> Any:
        """Route query to appropriate handler."""
        query_name = query.__class__.__name__
        handler = self.query_handlers.get(query_name)
        
        if not handler:
            raise ValueError(f"No handler for query: {query_name}")
        
        return await handler.handle(query)


# Global handler registry
_handler_registry: HandlerRegistry | None = None


def get_handler_registry(
    llm_router: Any = None,
    event_store: Any = None,
    pipeline_executor: PipelineExecutionPort | None = None,
) -> HandlerRegistry:
    """Get or create global handler registry."""
    global _handler_registry
    if _handler_registry is None:
        if llm_router is None:
            from reasoner.infrastructure.llm.router import ProviderRouter
            from reasoner.infrastructure.llm.ports import BaseLLMProvider, LLMResponse

            class _DummyProvider(BaseLLMProvider):
                def __init__(self):
                    super().__init__(model="dummy")

                @property
                def provider_name(self) -> str:
                    return "dummy"

                async def _complete_impl(self, messages, config):
                    return LLMResponse(
                        content="Dummy provider — configure API keys.",
                        model_used="dummy",
                        tokens_prompt=0,
                    )

                async def _complete_stream_impl(self, messages, config):
                    yield "Dummy provider — configure API keys."
                    return

            llm_router = ProviderRouter(primary=_DummyProvider())
        if pipeline_executor is None:
            pipeline_module = importlib.import_module("reasoner.api.execution.pipeline")
            pipeline_executor = pipeline_module.PipelineExecutionService()
        _handler_registry = HandlerRegistry(llm_router, event_store, pipeline_executor)
    return _handler_registry
