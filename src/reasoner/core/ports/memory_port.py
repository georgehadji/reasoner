"""Port interface for long-term memory — the neuro package provides the adapter.

Follows the same shape as ``model_registry_port.py``: core defines the port,
the concrete implementation is injected once at startup. Application-layer
code (orchestrator, streaming) depends on this port and never imports
``reasoner.neuro`` directly.

This replaces an HTTP loopback self-call. The pipeline used to reach memory by
POSTing to ``{internal_api_base_url}/api/neuro/{recall,learn}`` — its own
process, over the network. That cost a round-trip per run, and it silently did
nothing in CLI/headless mode, where no server is listening for the app to call.
The endpoints still exist for the Next proxy; the pipeline no longer uses them.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryPort(Protocol):
    """Port for long-term memory recall and persistence.

    Implemented by ``reasoner.neuro.server.NeuroService``.
    """

    async def recall(
        self,
        prompt: str,
        agent_id: str | None = None,
        max_results: int = 5,
        owner: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return context chunks relevant to *prompt*.

        Each chunk is ``{"content": str, "source": str, "relevance": float}``.
        Returns an empty list rather than raising when memory has nothing.
        """
        ...

    async def learn(
        self,
        prompt: str,
        response: str,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        owner: str | None = None,
    ) -> None:
        """Persist an exchange for later recall.

        *owner* scopes the tenant: agent_id is caller-supplied, so without it
        anyone knowing a conversation id could write into that conversation.
        """
        ...


# ── Dependency injection for application → neuro boundary ─────────────────
_MEMORY_PORT: MemoryPort | None = None


def set_memory_port(port: MemoryPort | None) -> None:
    """Inject the concrete memory adapter. Called once at startup."""
    global _MEMORY_PORT
    _MEMORY_PORT = port


def get_memory_port() -> MemoryPort | None:
    """Return the injected memory port, or None when memory is unavailable.

    Unlike the registry port this returns None instead of raising: memory is
    best-effort by design (a run proceeds fine without recalled context), and
    every caller already treats a miss as "no chunks". Raising here would only
    be caught and swallowed one frame up.
    """
    return _MEMORY_PORT
