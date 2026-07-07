"""Async test helpers and utilities."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, TypeVar

T = TypeVar("T")


def async_run(coro: Awaitable[T]) -> T:
    """Run an async coroutine synchronously (for use in sync test contexts)."""
    try:
        loop = asyncio.get_running_loop()
        # If we're already in an async context, create a new loop in a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


async def await_all(*aws: Awaitable[Any]) -> list[Any]:
    """Await multiple awaitables, returning results in order."""
    return await asyncio.gather(*aws, return_exceptions=True)


def create_future(result: T | None = None, exception: Exception | None = None) -> asyncio.Future[T]:
    """Create a pre-resolved Future for testing."""
    fut: asyncio.Future[T] = asyncio.get_event_loop().create_future()
    if exception is not None:
        fut.set_exception(exception)
    else:
        fut.set_result(result)  # type: ignore[arg-type]
    return fut
