"""Cancellation and WS broadcast wiring for streaming."""

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
