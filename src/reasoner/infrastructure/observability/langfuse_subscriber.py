"""
Langfuse EventBus Subscriber

Subscribes to LLMGenerationCompleted events and maps them to Langfuse traces.
"""

from __future__ import annotations

import os
import logging
import asyncio
from typing import Any, Dict, Optional

from langfuse import Langfuse
from langfuse.model import CreateTrace, CreateSpan, CreateGeneration, UpdateGeneration

from reasoner.core.events.domain_events import LLMGenerationCompleted, PipelineEventType
from reasoner.application.event_bus.bus import EventBus

logger = logging.getLogger(__name__)

# Global Langfuse client instance
_langfuse_client: Optional[Langfuse] = None
_langfuse_lock = asyncio.Lock()
_is_langfuse_enabled = False

def _setup_langfuse() -> None:
    global _langfuse_client, _is_langfuse_enabled
    if _langfuse_client is None:
        public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
        secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
        host = os.environ.get("LANGFUSE_HOST")

        if public_key and secret_key:
            try:
                _langfuse_client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
                _is_langfuse_enabled = True
                logger.info("Langfuse client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse client: {e}")
                _is_langfuse_enabled = False
        else:
            logger.info("LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not found. Langfuse disabled.")
            _is_langfuse_enabled = False


class LangfuseSubscriber:
    """
    Subscribes to relevant domain events and sends them to Langfuse.
    """

    def __init__(self):
        _setup_langfuse() # Initialize Langfuse when subscriber is created
        if not _is_langfuse_enabled:
            logger.warning("LangfuseSubscriber initialized but Langfuse is disabled.")
        
        self._active_traces: Dict[str, Any] = {}
        self._active_spans: Dict[str, Any] = {}

    async def handle_llm_generation_completed(self, event: LLMGenerationCompleted) -> None:
        if not _is_langfuse_enabled or _langfuse_client is None: return

        trace_id = event.pipeline_id
        span_id = f"{trace_id}-{event.phase_name}"

        # Create or retrieve trace
        if trace_id not in self._active_traces:
            self._active_traces[trace_id] = _langfuse_client.trace(
                CreateTrace(id=trace_id, name=f"Pipeline: {trace_id}", metadata={"problem": ""}) # Problem field is updated later if needed
            )
            logger.debug(f"Langfuse: Created trace {trace_id}")

        # Create or retrieve span for the phase
        if span_id not in self._active_spans:
            self._active_spans[span_id] = self._active_traces[trace_id].span(
                CreateSpan(id=span_id, name=f"Phase: {event.phase_name}", input={"system_prompt": event.system_prompt, "user_prompt": event.user_prompt})
            )
            logger.debug(f"Langfuse: Created span {span_id}")

        # Create generation
        try:
            generation = self._active_spans[span_id].generation(
                CreateGeneration(
                    name=f"LLM Call: {event.model_name}",
                    model=event.model_name,
                    input={
                        "system_prompt": event.system_prompt,
                        "user_prompt": event.user_prompt,
                    },
                    output={
                        "raw_response": event.raw_response,
                    },
                    usage={
                        "promptTokens": event.prompt_tokens,
                        "completionTokens": event.completion_tokens,
                        "totalTokens": event.total_tokens,
                    },
                    metadata={
                        "cost": event.cost,
                        "duration": event.duration_seconds,
                        "cached": event.metadata.get("cached", False),
                        "degraded": event.metadata.get("degraded", False),
                        "empty_response": event.metadata.get("empty_response", False),
                        "cascading": event.metadata.get("cascading", False),
                        "error": event.metadata.get("error"),
                    },
                    start_time=event.timestamp, # Use event timestamp for start time
                    end_time=event.timestamp + event.duration_seconds if event.duration_seconds is not None else event.timestamp,
                )
            )
            logger.debug(f"Langfuse: Created generation {generation.id}")
            # For Langfuse, we need to explicitly update the generation when it's completed.
            # The `create_generation` call implicitly starts a new generation.
            # We can use update_generation to set the output and end_time.
            generation.update(UpdateGeneration(
                output={
                    "raw_response": event.raw_response,
                },
                usage={
                    "promptTokens": event.prompt_tokens,
                    "completionTokens": event.completion_tokens,
                    "totalTokens": event.total_tokens,
                },
                end_time=event.timestamp + event.duration_seconds if event.duration_seconds is not None else event.timestamp,
            ))
            logger.debug(f"Langfuse: Updated generation {generation.id}")

        except Exception as e:
            logger.error(f"Langfuse: Failed to send generation event for pipeline {trace_id}, phase {event.phase_name}: {e}")

    async def handle_pipeline_started(self, event: Any) -> None:
        # Initial trace creation, ensuring the trace exists for subsequent spans/generations
        if not _is_langfuse_enabled or _langfuse_client is None: return
        trace_id = event.aggregate_id
        if trace_id not in self._active_traces:
            self._active_traces[trace_id] = _langfuse_client.trace(
                CreateTrace(id=trace_id, name=f"Pipeline: {trace_id}", metadata={"problem": event.problem, "preset": event.preset, "method": event.method})
            )
            logger.debug(f"Langfuse: Initialized trace {trace_id} from PipelineStarted event.")

    async def handle_pipeline_completed(self, event: Any) -> None:
        if not _is_langfuse_enabled or _langfuse_client is None: return
        trace_id = event.aggregate_id
        if trace_id in self._active_traces:
            # Optionally update trace with final status or metadata
            # For now, just ensure it's flushed
            self._active_traces[trace_id].update(
                name=f"Pipeline: {trace_id} (Completed)",
                output=event.solution,
                metadata={
                    "total_tokens": event.total_tokens,
                    "total_duration_seconds": event.total_duration_seconds,
                    "phases_completed": event.phases_completed,
                }
            )
            _langfuse_client.flush() # Ensure all events are sent
            del self._active_traces[trace_id] # Clean up
            logger.debug(f"Langfuse: Flushed and cleaned up trace {trace_id}")

    async def handle_pipeline_failed(self, event: Any) -> None:
        if not _is_langfuse_enabled or _langfuse_client is None: return
        trace_id = event.aggregate_id
        if trace_id in self._active_traces:
            # Mark trace as failed
            self._active_traces[trace_id].update(
                name=f"Pipeline: {trace_id} (Failed)",
                status="ERROR",
                status_message=event.error,
                metadata={
                    "phase_at_failure": event.phase_at_failure,
                    "phases_completed": event.phases_completed,
                }
            )
            _langfuse_client.flush() # Ensure all events are sent
            del self._active_traces[trace_id] # Clean up
            logger.debug(f"Langfuse: Flushed and cleaned up failed trace {trace_id}")


_langfuse_subscriber: Optional[LangfuseSubscriber] = None
_subscriber_lock = asyncio.Lock()

async def get_langfuse_subscriber() -> LangfuseSubscriber:
    global _langfuse_subscriber
    async with _subscriber_lock:
        if _langfuse_subscriber is None:
            _langfuse_subscriber = LangfuseSubscriber()
    return _langfuse_subscriber
