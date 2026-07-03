import sys
import re
from pathlib import Path

def main():
    repo_root = Path(__file__).parent.parent.resolve()
    streaming_path = repo_root / "src" / "reasoner" / "api" / "streaming.py"
    
    with open(streaming_path, "r", encoding="utf-8") as f:
        content = f.read()

    # The new run_stream implementation
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

    # We want to keep everything up to `# Creative-writing model tiers`
    # Because _stream_direct_answer, _stream_web_search_results, run_stream follow that.
    
    start_match = re.search(r'# Creative-writing model tiers', content)
    if not start_match:
        print("Could not find '# Creative-writing model tiers'")
        return
        
    start_idx = start_match.start()
    
    # And we want to keep everything from `async def run_followup_stream` to the end
    end_match = re.search(r'async def run_followup_stream\(', content[start_idx:])
    if not end_match:
        print("Could not find 'run_followup_stream'")
        return
        
    end_idx = start_idx + end_match.start()
    
    new_content = content[:start_idx] + "\n" + new_run_stream + "\n\n" + content[end_idx:]
    
    with open(streaming_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print("Fixed streaming.py")

if __name__ == "__main__":
    main()
