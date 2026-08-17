"""Bounded background queue for document semantic-search indexing.

security-remediation-plan.md Phase 4 item 4: replaces an unbounded
``asyncio.create_task(store.index_file(...))`` per upload (no cap, no
backpressure) with a fixed-size queue and a small worker pool. A full queue
drops the newest job and logs rather than blocking the upload response or
letting concurrent indexing tasks grow without bound — semantic search
degrades gracefully; the upload itself always still succeeds.

Lazily started on first use, same pattern as
``infrastructure/websocket/manager.py``'s ``get_websocket_manager()``.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[tuple[str, str]] | None = None
_workers: list[asyncio.Task] = []


def _ensure_started() -> asyncio.Queue[tuple[str, str]]:
    global _queue
    if _queue is not None:
        return _queue

    from reasoner.core.settings import settings

    _queue = asyncio.Queue(maxsize=settings.DOCUMENT_INDEX_QUEUE_MAXSIZE)
    for i in range(max(1, settings.DOCUMENT_INDEX_WORKER_COUNT)):
        task = asyncio.create_task(_worker_loop(_queue), name=f"doc-index-worker-{i}")
        _workers.append(task)
    return _queue


async def _worker_loop(queue: asyncio.Queue[tuple[str, str]]) -> None:
    from reasoner.documents.vector_store import DocumentVectorStore

    store = DocumentVectorStore()
    while True:
        file_id, text = await queue.get()
        try:
            await store.index_file(file_id, text)
        except Exception as exc:
            logger.warning("Background document indexing failed for %s: %s", file_id, exc)
        finally:
            queue.task_done()


def enqueue_index_job(file_id: str, text: str) -> bool:
    """Schedule a document for background indexing.

    Returns False (and drops the job, logging a warning) when the queue is
    full instead of blocking the caller or spawning an unbounded task --
    the upload itself must never wait on or fail because of indexing
    capacity.
    """
    queue = _ensure_started()
    try:
        queue.put_nowait((file_id, text))
        return True
    except asyncio.QueueFull:
        logger.warning(
            "Document index queue full (maxsize=%d); dropping indexing job for %s. "
            "The file is still saved and retrievable; only semantic search over it is skipped.",
            queue.maxsize,
            file_id,
        )
        return False


def _reset_for_tests() -> None:
    """Drop the queue/workers so tests get a fresh instance. Not for
    production use."""
    global _queue
    for task in _workers:
        task.cancel()
    _workers.clear()
    _queue = None


__all__ = ["enqueue_index_job"]
