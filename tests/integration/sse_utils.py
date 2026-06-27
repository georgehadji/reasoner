"""Async SSE stream collector for integration tests."""

from __future__ import annotations

import json
from typing import Any

import httpx


class SSEEvent:
    """A single SSE event parsed from the stream."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.data: dict[str, Any] = {}
        if raw.startswith("data: "):
            try:
                self.data = json.loads(raw[6:])
            except json.JSONDecodeError:
                pass

    @property
    def type(self) -> str:
        return self.data.get("type", "")

    @property
    def is_error(self) -> bool:
        return self.type == "error"

    @property
    def is_done(self) -> bool:
        return self.type in ("done", "end")

    @property
    def is_phase_complete(self) -> bool:
        return self.type == "phase_complete"

    @property
    def is_phase_start(self) -> bool:
        return self.type == "phase_start"

    @property
    def phase_name(self) -> str:
        return self.data.get("name", "")


class SSECollector:
    """Collects and indexes SSE events from a streamed response."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.events: list[SSEEvent] = []
        self.errors: list[str] = []
        self.done_event: dict[str, Any] | None = None
        self.phase_start_names: set[str] = set()
        self.phase_complete_names: set[str] = set()

    async def collect(self) -> None:
        """Read all SSE lines until done/end/error."""
        async for line in self._response.aiter_lines():
            ev = SSEEvent(line)
            if not ev.data:
                continue
            self.events.append(ev)

            if ev.type == "phase_start":
                self.phase_start_names.add(ev.phase_name)
            elif ev.type == "phase_complete":
                self.phase_complete_names.add(ev.phase_name)
            elif ev.is_error:
                self.errors.append(ev.data.get("error", str(ev.data)))
            elif ev.is_done:
                self.done_event = ev.data
                break

    @property
    def total_phases(self) -> int:
        return len(self.phase_complete_names)

    @property
    def total_tokens(self) -> dict[str, int]:
        if self.done_event:
            return self.done_event.get("total_tokens", {})
        return {}


async def collect_pipeline_events(
    api_client: httpx.AsyncClient,
    csrf_token: str,
    problem: str,
    preset: str,
) -> SSECollector:
    """POST /api/run and collect all SSE events into a SSECollector."""
    response = await api_client.post(
        "/api/run",
        json={
            "problem": problem,
            "preset": preset,
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200, (
        f"Pipeline POST returned {response.status_code}: {response.text[:200]}"
    )
    collector = SSECollector(response)
    await collector.collect()
    return collector
