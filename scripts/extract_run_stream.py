import sys
import re
from pathlib import Path

def main():
    repo_root = Path(__file__).parent.parent.resolve()
    streaming_path = repo_root / "src" / "reasoner" / "api" / "streaming.py"
    
    with open(streaming_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the full body of run_stream
    # We find the start of run_stream
    start_match = re.search(r'async def run_stream\(.*?\n\) -> AsyncGenerator\[str, None\]:', content, re.DOTALL)
    if not start_match:
        print("Could not find run_stream")
        return
        
    start_idx = start_match.end()
    
    # run_stream ends before run_followup_stream
    end_match = re.search(r'async def run_followup_stream\(', content[start_idx:])
    if not end_match:
        print("Could not find run_followup_stream")
        return
        
    end_idx = start_idx + end_match.start()
    
    run_stream_body = content[start_idx:end_idx]
    
    # We need to adapt run_stream_body for PipelineExecutionService
    # Replacements:
    # `yield _event(payload)` -> `await sse_emit(payload)`
    # `yield _ka` -> `await sse_emit(_ka)` (Wait, `run_phase_with_keepalive` yields formatted SSE strings? No, wait. 
    # Let's just make sse_emit accept dict and format it later, or accept both. Let's make sse_emit accept dict, but if we need to emit raw string...
    # `yield _event(start_payload)` -> `await sse_emit(start_payload)`
    
    # `req.` -> `command.` (mostly)
    # Actually, we should just reconstruct `req` inside `PipelineExecutionService` from `command` to minimize changes!
    
    execution_service_content = f"""
import asyncio
import uuid
import logging
import time
import hashlib
import json
from typing import Callable, Awaitable, Any

from reasoner.application.commands import RunPipelineCommand
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.core.logging_utils import set_correlation_id
from reasoner.api.schemas import RunRequest
from reasoner.api.streaming import (
    _stream_direct_answer, _stream_web_search_results, _get_phase_subagents
)
from reasoner.api.history import HistoryEntry, _save_history_entry, _save_pipeline_owner, HISTORY_DIR
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store
from reasoner.core.events.domain_events import make_event, EventType
from reasoner.api.sse_utils import _event, _broadcast_ws, _persist_event
from reasoner.api.phase_executor import get_phase_start_models, get_critical_phases, run_phase_with_keepalive
from reasoner.core.constants import TRUNCATION, get_phase_retry_budget, get_phase_timeout
from reasoner.exceptions import classify_error, is_retryable
from reasoner.core.exceptions import ErrorCode, error_code_for_exception
from reasoner.quality import PhaseMonitor, reset_phase_state
from reasoner.presets import get_method_from_preset

logger = logging.getLogger(__name__)

class PipelineExecutionService:
    async def execute_run(
        self,
        command: RunPipelineCommand,
        router: ProviderRouter,
        sse_emit: Callable[[dict | str], Awaitable[None]],
        user_id: str | None = None,
        initial_state: PipelineState | None = None
    ) -> PipelineState:
        # Reconstruct req for compatibility with existing code
        req = RunRequest(
            problem=command.problem,
            preset=command.preset,
            method=command.method,
            top_k=command.top_k,
            source_type=command.source_type,
            domain=command.domain,
            sequential=not command.parallel,
            client_run_id=command.command_id
        )
        
        preset_service = PresetService()
        pipeline_service = PipelineService()
        request = None
        
{run_stream_body}
        
        return state
"""

    # Replace `yield _event(x)` with `await sse_emit(x)`
    # Replace `yield chunk` with `await sse_emit(chunk)`
    # Replace `yield _ka` with `await sse_emit(_ka)`
    
    execution_service_content = re.sub(r'yield _event\((.*?)\)', r'await sse_emit(\1)', execution_service_content)
    execution_service_content = re.sub(r'yield chunk', r'await sse_emit(chunk)', execution_service_content)
    execution_service_content = re.sub(r'yield _ka', r'await sse_emit(_ka)', execution_service_content)
    
    # Remove the NotImplementedError at the start
    execution_service_content = re.sub(
        r'    if not _settings\.CQRS_BYPASS_STREAMING:.*?raise NotImplementedError\(.*?C1\."\n        \)', 
        '', 
        execution_service_content, 
        flags=re.DOTALL
    )

    with open(repo_root / "src" / "reasoner" / "application" / "services" / "pipeline_execution_service.py", "w", encoding="utf-8") as f:
        f.write(execution_service_content)
        
    print("Created pipeline_execution_service.py")

    # Now rewrite api/streaming.py
    
    new_run_stream = """async def run_stream(
    req: RunRequest,
    initial_state: PipelineState | None = None,
    user_id: str | None = None,
    preset_service: PresetService | None = None,
    pipeline_service: PipelineService | None = None,
    request=None,
) -> AsyncGenerator[str, None]:
    from reasoner.application.commands import RunPipelineCommand
    from reasoner.application.handlers.handlers import get_handler_registry
    import asyncio
    import uuid
    
    run_id = req.client_run_id or str(uuid.uuid4())
    command = RunPipelineCommand(
        command_id=run_id,
        problem=req.problem,
        preset=req.preset,
        method=getattr(req, "method", None),
        top_k=getattr(req, "top_k", 2),
        source_type=getattr(req, "source_type", "general"),
        domain=getattr(req, "domain", None),
        parallel=not getattr(req, "sequential", False)
    )
    
    queue = asyncio.Queue()
    
    async def sse_emit(event: dict | str) -> None:
        if isinstance(event, dict):
            await queue.put(_event(event))
        else:
            await queue.put(event)
            
    async def run_task():
        try:
            registry = get_handler_registry()
            handler = registry.command_handlers["RunPipelineCommand"]
            await handler.handle(command, sse_emit=sse_emit)
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            await queue.put(None)
            
    task = asyncio.create_task(run_task())
    
    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        yield chunk

"""
    new_streaming_content = content[:start_match.start()] + new_run_stream + content[end_idx:]
    with open(streaming_path, "w", encoding="utf-8") as f:
        f.write(new_streaming_content)
        
    print("Updated streaming.py")

if __name__ == "__main__":
    main()
