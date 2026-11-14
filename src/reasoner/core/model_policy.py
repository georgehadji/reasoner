"""Per-run restriction on which geopolitical model blocs may be called.

A Western-only run (a preset tagged ``western-only``, or a request with
``western_only=True``) sets ``ALLOWED_BLOCS`` to ``{"US", "EU"}`` for its
whole duration. ``infrastructure.llm.registry.build_provider`` checks it, and
every model a run touches is built there, so the restriction holds for preset
roles, fallbacks, cascades, search decomposition, OCR and direct answers alike.

A ``ContextVar`` rather than a parameter: asyncio copies the context into every
task created inside the run, so parallel generators inherit it without each
call site threading an argument through.

Never construct a provider around ``build_provider`` in a code path a run can
reach; that would bypass this check silently.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

WESTERN_BLOCS: frozenset[str] = frozenset({"US", "EU"})
WESTERN_TAG = "western-only"
WESTERN_MEMORY_SUFFIX = "-western"

ALLOWED_BLOCS: ContextVar[frozenset[str] | None] = ContextVar("allowed_blocs", default=None)


class ModelNotAllowedError(ValueError):
    """A model outside the run's allowed blocs was requested."""


def allowed_blocs() -> frozenset[str] | None:
    """The blocs this run may call, or ``None`` when unrestricted."""
    return ALLOWED_BLOCS.get()


def is_allowed(bloc: str) -> bool:
    allowed = ALLOWED_BLOCS.get()
    return allowed is None or bloc in allowed


def run_blocs(preset_id: str | None) -> frozenset[str] | None:
    """Model blocs a run of this preset may call; None means unrestricted.

    Same id rule as domain.preset_core.is_western_preset (core may not import
    domain); tests/unit/test_model_policy.py checks they agree.
    """
    return WESTERN_BLOCS if preset_id and "-western-" in preset_id else None


def memory_agent_id(agent_id: str | None) -> str | None:
    """The Neuro agent id a run reads and writes memory under.

    Western runs use their own store: it is embedded by a different model, and
    vectors from two embedding models cannot be compared. No id stays no id,
    so an anonymous run still gets no tenant.
    """
    if agent_id and ALLOWED_BLOCS.get() is not None:
        return f"{agent_id}{WESTERN_MEMORY_SUFFIX}"
    return agent_id


def is_western_memory(agent_id: str | None) -> bool:
    return bool(agent_id) and agent_id.endswith(WESTERN_MEMORY_SUFFIX)


@contextmanager
def restrict_blocs(blocs: frozenset[str] | None) -> Iterator[None]:
    """Restrict model blocs for the enclosed block (no-op when ``blocs`` is None)."""
    if blocs is None:
        yield
        return
    token = ALLOWED_BLOCS.set(blocs)
    try:
        yield
    finally:
        ALLOWED_BLOCS.reset(token)
