"""Port interface for model registry — infrastructure provides concrete implementation.

Follows the same shape as ``circuit_breaker_port.py``: the core layer defines the
port, the infrastructure layer provides the adapter. Application/domain layers
depend on this port, never on ``infrastructure.llm.registry`` directly.

Security note: the port boundary is the natural enforcement point for the model
allowlist. ``get_provider`` rejects unknown model IDs here (via the adapter's
delegation to ``build_provider``), so no call site can silently dispatch to an
arbitrary provider by typo or by user-controlled input.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelRegistryPort(Protocol):
    """Port for model registry access.

    Implemented by ``infrastructure.llm.registry.RegistryAdapter``. The
    application layer depends on this port, not on the concrete registry.
    """

    def get_provider(self, model_id: str, api_key: str | None = None) -> Any:
        """Build a provider instance from a model ID string.

        Raises ``ValueError`` for unknown model IDs (allowlist enforcement).
        """
        ...

    def contains(self, model_id: str) -> bool:
        """Return True if *model_id* is a known registry entry."""
        ...

    def entry(self, model_id: str) -> dict[str, Any] | None:
        """Return the registry config entry for *model_id*, or None if unknown."""
        ...

    def vendor_of(self, model_id: str) -> str:
        """Return the OpenRouter vendor prefix *model_id* resolves to (e.g. ``"mistralai"``).

        Resolves through the registry's served-model string, not the alias, so
        cross-vendor aliases (e.g. an alias named after one lab that is actually
        routed to another) resolve correctly. Unknown model IDs return the ID
        itself, unchanged from ``infrastructure.llm.registry._vendor_of``.
        """
        ...

    def bloc_of(self, model_id: str) -> str:
        """Return the geopolitical training bloc for *model_id*: US, CN, EU, or OTHER."""
        ...

    def resolved_model_of(self, model_id: str) -> str:
        """Return the full ``vendor/model`` string *model_id* resolves to."""
        ...

    def deprecated_aliases(self) -> dict[str, str | None]:
        """Map each deprecated alias to a drop-in replacement, or None.

        A deprecated alias still resolves — ``routing`` is a public request
        field and callers may still name one — but its own name misstates the
        version or tier it resolves to.

        The value is an alias that serves the same model *and behaves
        identically*, so a caller can swap to it safely. It is ``None`` when no
        such alias exists: some entries share a served model with an
        honestly-named alias that differs in ``extra_body`` (reasoning effort,
        say), and swapping there would change cost and latency, not just the
        name.
        """
        ...


# ── Dependency injection for application → infrastructure boundary ────────
# Mirrors core/search.py's set_build_provider() precedent: the concrete
# adapter is injected once at startup (api/__init__.py lifespan, main.py),
# so application-layer code never imports infrastructure.llm.registry.
_REGISTRY_PORT: ModelRegistryPort | None = None


def set_model_registry_port(port: ModelRegistryPort) -> None:
    """Inject the concrete registry adapter. Called once at startup."""
    global _REGISTRY_PORT
    _REGISTRY_PORT = port


def get_model_registry_port() -> ModelRegistryPort:
    """Return the injected registry port.

    Raises RuntimeError if no adapter has been injected yet — fail loud
    rather than silently falling back to a direct infrastructure import.
    """
    if _REGISTRY_PORT is None:
        raise RuntimeError(
            "ModelRegistryPort not injected — call set_model_registry_port() "
            "at application startup (see api/__init__.py lifespan or main.py)."
        )
    return _REGISTRY_PORT
