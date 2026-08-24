"""
EventBusReplayService — Replay dead-letter events through the EventBus.

Admin-scoped operations: inspect and replay events that exhausted all retries.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class EventBusReplayService:
    """Inspect and replay dead-letter events.

    Reads the dead-letter JSONL file, re-publishes events through the bus,
    and moves successfully replayed lines to a .replayed sidecar for
    at-least-once idempotency.
    """

    def __init__(self, dead_letter_path: Path | None = None):
        if dead_letter_path is None:
            self._path = Path(__file__).parent.parent.parent / "logs" / "dead_letter_events.jsonl"
        else:
            self._path = dead_letter_path
        self._replayed_sidecar = self._path.with_suffix(".replayed")
        self._write_lock = asyncio.Lock()

    async def list_events(
        self,
        limit: int = 100,
        offset: int = 0,
        event_type_filter: str | None = None,
    ) -> dict:
        """List dead-letter events with pagination.

        Returns:
            dict with "events" (list of dicts), "total" (int), and "replayed_count" (int).
        """
        events = []
        replayed_ids = await self._load_replayed_ids()

        if not self._path.exists():
            return {"events": [], "total": 0, "replayed_count": len(replayed_ids)}

        try:
            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
        except Exception as exc:
            logger.error("Failed to read dead-letter file: %s", exc)
            return {"events": [], "total": 0, "replayed_count": len(replayed_ids)}

        total = 0
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Apply optional filter
            if event_type_filter and entry.get("event_type") != event_type_filter:
                continue

            # Track replayed status
            entry["replayed"] = entry.get("event_id") in replayed_ids

            total += 1
            if total > offset and len(events) < limit:
                events.append(entry)

        return {
            "events": events,
            "total": total,
            "replayed_count": len(replayed_ids),
        }

    async def replay_events(
        self,
        event_ids: list[str] | None = None,
        max_count: int = 50,
    ) -> dict:
        """Replay dead-letter events through the EventBus.

        Args:
            event_ids: Specific event IDs to replay (None = replay all unreplayed).
            max_count: Maximum events to replay in one batch.

        Returns:
            dict with "replayed" (int), "failed" (int), "errors" (list).
        """
        from reasoner.application.event_bus.bus import get_event_bus
        from reasoner.core.events.domain_events import ALL_EVENT_TYPES, DomainEvent

        bus = get_event_bus()
        replayed_ids = await self._load_replayed_ids()

        if not self._path.exists():
            return {"replayed": 0, "failed": 0, "errors": []}

        try:
            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
        except Exception as exc:
            return {"replayed": 0, "failed": 0, "errors": [str(exc)]}

        results = {"replayed": 0, "failed": 0, "errors": []}

        for line in lines:
            if not line.strip():
                continue
            if max_count is not None and results["replayed"] + results["failed"] >= max_count:
                break

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_id = entry.get("event_id")
            # Skip already replayed
            if event_id in replayed_ids:
                continue
            # Skip if not in the requested list
            if event_ids is not None and event_id not in event_ids:
                continue

            try:
                # Reconstruct a DomainEvent from the dead-letter entry
                event_type_str = entry.get("event_type", "")
                event_type = ALL_EVENT_TYPES.get(event_type_str)
                if event_type is None:
                    results["failed"] += 1
                    results["errors"].append(f"Unknown event type: {event_type_str}")
                    continue

                event = DomainEvent(
                    event_id=event_id or "",
                    event_type=event_type,
                    timestamp=entry.get("timestamp", 0.0),
                    aggregate_id=entry.get("aggregate_id", ""),
                    version=0,
                    metadata={},
                )
                await bus.publish(event)
                results["replayed"] += 1

                # Mark as replayed in sidecar
                await self._mark_replayed(event_id)
                if event_id:
                    replayed_ids.add(event_id)  # keep in-memory set current for batch

            except Exception as exc:
                results["failed"] += 1
                results["errors"].append(f"{event_id}: {exc}")

        return results

    async def _load_replayed_ids(self) -> set[str]:
        """Load the set of already-replayed event IDs from the sidecar."""
        if not self._replayed_sidecar.exists():
            return set()
        try:
            content = self._replayed_sidecar.read_text(encoding="utf-8").strip()
            return set(line.strip() for line in content.split("\n") if line.strip())
        except Exception:
            return set()

    async def _mark_replayed(self, event_id: str | None) -> None:
        """Append an event ID to the replayed sidecar."""
        if not event_id:
            return
        try:
            async with self._write_lock:
                await asyncio.to_thread(
                    self._append_to_sidecar, self._replayed_sidecar, event_id
                )
        except Exception as exc:
            logger.warning("Failed to mark event %s as replayed: %s", event_id, exc)

    @staticmethod
    def _append_to_sidecar(path: Path, event_id: str) -> None:
        """Append an event ID to the sidecar file (runs in a thread)."""
        with open(path, "a", encoding="utf-8") as f:
            f.write(event_id + "\n")
            f.flush()
