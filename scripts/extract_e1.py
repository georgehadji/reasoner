import sys
import re
from pathlib import Path

def main():
    repo_root = Path(__file__).parent.parent.resolve()
    streaming_path = repo_root / "src" / "reasoner" / "api" / "streaming.py"
    
    with open(streaming_path, "r", encoding="utf-8") as f:
        content = f.read()

    # direct.py
    # Look for _stream_direct_answer
    match_direct = re.search(r'async def _stream_direct_answer\(.*?return', content, re.DOTALL)
    direct_code = ""
    if match_direct:
        direct_code = match_direct.group(0)
    
    direct_content = f"""\"\"\"Direct answer streaming execution.\"\"\"

import time
import asyncio
from typing import AsyncGenerator
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.phases._shared import build_followup_context
from reasoner.api.sse_utils import _event

{direct_code}
"""
    with open(repo_root / "src" / "reasoner" / "api" / "execution" / "direct.py", "w", encoding="utf-8") as f:
        f.write(direct_content)

    # web_search.py
    match_web = re.search(r'async def _stream_web_search_results\(.*?return', content, re.DOTALL)
    web_code = ""
    if match_web:
        web_code = match_web.group(0)
    
    web_search_content = f"""\"\"\"Web search streaming execution.\"\"\"

import asyncio
from typing import AsyncGenerator
from reasoner.application.services.search_service import SearchService

_search_service = SearchService()

{web_code}
"""
    with open(repo_root / "src" / "reasoner" / "api" / "execution" / "web_search.py", "w", encoding="utf-8") as f:
        f.write(web_search_content)

    # cancel.py (cancellation and WS broadcast logic)
    # The instruction says "run cancellation + WS broadcast wiring".
    # This might include `_broadcast_ws`, but `_broadcast_ws` is in `sse_utils.py` currently!
    # Wait, the instruction says "run cancellation + WS broadcast wiring".
    # In `streaming.py`, there is `_run_tasks: set[asyncio.Task] = set()` and `_tracked_broadcast`.
    
    cancel_content = f"""\"\"\"Cancellation and WS broadcast wiring for streaming.\"\"\"

import asyncio
from typing import Awaitable, Callable
from reasoner.api.sse_utils import _broadcast_ws

class StreamingConnectionContext:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._run_tasks: set[asyncio.Task] = set()
        
    def tracked_broadcast(self, payload: dict) -> None:
        coro = _broadcast_ws(self.run_id, payload, _tasks=self._run_tasks)
        task = asyncio.create_task(coro)
        self._run_tasks.add(task)
        task.add_done_callback(self._run_tasks.discard)
        
    async def cleanup(self) -> None:
        for t in list(self._run_tasks):
            if not t.done():
                t.cancel()
        if self._run_tasks:
            await asyncio.gather(*self._run_tasks, return_exceptions=True)
"""
    with open(repo_root / "src" / "reasoner" / "api" / "execution" / "cancel.py", "w", encoding="utf-8") as f:
        f.write(cancel_content)

    # pipeline.py (main pipeline SSE adaptation)
    # This might mean my PipelineExecutionService should have been `api/execution/pipeline.py`!
    
    # We will just write a small stub or copy pipeline_execution_service there?
    # No, we already moved logic into PipelineExecutionService which is in application layer.
    # The instruction says "api/execution/pipeline.py # main pipeline SSE adaptation".
    # I can just leave it in application/services for now since it works and is better layered (CommandHandler calls Application Service), 
    # but to follow the exact E1 checklist, I could rename `application/services/pipeline_execution_service.py` to `api/execution/pipeline.py`.
    
    print("Extracted to direct.py, web_search.py, cancel.py")

if __name__ == "__main__":
    main()
