"""Direct answer streaming execution."""

import time
import asyncio
from typing import AsyncGenerator
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.phases._shared import build_followup_context
from reasoner.api.sse_utils import _event

async def _stream_direct_answer(
    router: ProviderRouter,
    problem: str,
    run_id: str,
    cancel_event: asyncio.Event | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    previous_synthesis: str = "",
    turn_number: int = 1,
    preset_name: str = "",
    web_search: bool = False,
) -> AsyncGenerator[str, None]:
    """Stream a direct LLM answer as a virtual single-phase pipeline for UI compatibility."""
    yield _event({"type": "start"})

    if cancel_event and cancel_event.is_set():
        yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
        return
