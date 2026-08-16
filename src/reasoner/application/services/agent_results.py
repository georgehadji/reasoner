"""Assemble an aggregated run result from a decoded SSE event stream.

Used by ``POST /api/agent/run/sync``, which runs a pipeline and returns one
JSON object instead of a stream.

The terminal ``done`` frame is **not** the source for a run's conclusions. It
carries only ``type``, ``errors``, ``total_tokens``, ``duration``,
``total_cost_usd``, and ``phase_costs``. The substance lives on phase payloads:

* ``core_solution``, ``critical_insights``, ``open_questions`` — together in the
  synthesis payload built by ``_ser_synthesis``.
* ``citations`` — on their own phase via ``_ser_5``, which emits no
  ``core_solution``, so they cannot be read off the synthesis payload.

These are pure functions over decoded events so they can be tested without
importing the FastAPI app, which is expensive.
"""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


def coerce_string_list(value: object) -> list[str]:
    """Coerce a serialized phase field to ``list[str]``, dropping anything else.

    Phase payloads are LLM-derived, so a field that is normally a list of
    strings can arrive malformed. ``RunResult`` declares ``list[str]``, and
    letting a bad element through would turn a completed, already-paid-for run
    into a 500.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def coerce_dict_list(value: object) -> list[dict]:
    """Coerce a serialized phase field to ``list[dict]``. See :func:`coerce_string_list`."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def extract_synthesis_payload(events: list[dict]) -> dict:
    """Return the phase payload holding the run's conclusions.

    Searched in reverse so the final synthesis wins over any earlier partial.
    The whole payload is returned rather than just the solution text, because
    ``critical_insights`` and ``open_questions`` sit beside ``core_solution`` in
    the same dict.

    Returns an empty dict when no phase produced a solution — a run that
    crashed before synthesising has conclusions to report from nowhere.
    """
    for event in reversed(events):
        if event.get("type") != "phase_complete":
            continue

        data = event.get("data")
        if not isinstance(data, dict):
            continue

        core = data.get("core_solution", "")
        # Some methods nest the solution one level deeper.
        if isinstance(core, dict):
            core = core.get("core_solution", "") or core.get("synthesis", "")

        if core and isinstance(core, str):
            return {**data, "core_solution": core}

    return {}


def extract_citations(events: list[dict]) -> list[dict]:
    """Find citations, which ride their own phase rather than the synthesis one.

    ``_ser_5`` emits ``{"citations": [...]}`` on a phase carrying no
    ``core_solution``, so a scan separate from :func:`extract_synthesis_payload`
    is required. Only web-grounded methods populate this at all.
    """
    for event in reversed(events):
        if event.get("type") != "phase_complete":
            continue

        data = event.get("data")
        if isinstance(data, dict) and data.get("citations"):
            found = coerce_dict_list(data["citations"])
            if found:
                return found

    return []


def extract_method(events: Sequence[Mapping[str, Any]]) -> str | None:
    """Return the reasoning method HyperGate selected, if it announced one.

    Direct and web-search routes never emit ``method_selected``, so None is a
    legitimate answer rather than a missing value.
    """
    for event in events:
        if event.get("type") == "method_selected":
            method = event.get("method")
            if isinstance(method, str) and method:
                return method
    return None


def extract_models_used(events: Sequence[Mapping[str, Any]]) -> list[str]:
    """Collect every model named on a phase, in first-seen order."""
    seen: dict[str, None] = {}
    for event in events:
        if event.get("type") != "phase_complete":
            continue
        data = event.get("data")
        models = data.get("models") if isinstance(data, dict) else None
        if models is None:
            models = event.get("models")
        for model in coerce_string_list(models):
            seen.setdefault(model, None)
    return list(seen)


def _coerce_number(value: object) -> float:
    """Read a numeric telemetry field, defaulting to 0.0 rather than raising.

    Bools are excluded deliberately: ``True`` is an ``int`` in Python, and a
    malformed frame must not turn into a cost of one dollar.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def extract_terminal_frame(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return the run's terminal frame, or an empty mapping if it never arrived.

    A pipeline that crashed hard emits a reduced ``done`` frame carrying only
    ``type`` and ``errors``, so every key but ``type`` is optional at read time.
    """
    for event in reversed(events):
        if event.get("type") in ("done", "end"):
            return event
    return {}


@dataclass(frozen=True)
class RunSummary:
    """Everything one pipeline run concluded, folded out of its event stream.

    Immutable and I/O-free: the same value is returned to an HTTP caller, an
    MCP tool, and a test, so it must not carry adapter-specific shape. Sequence
    fields are tuples so a caller cannot mutate a result another adapter is
    still reading.
    """

    preset: str
    method: str | None = None
    synthesis: str = ""
    critical_insights: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    claim_labels: Mapping[str, str] = types.MappingProxyType({})
    action_blueprint: tuple[Mapping[str, Any], ...] = ()
    citations: tuple[Mapping[str, Any], ...] = ()
    models_used: tuple[str, ...] = ()
    total_tokens: Mapping[str, int] = types.MappingProxyType(
        {"input": 0, "output": 0, "total": 0}
    )
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    errors: tuple[str, ...] = ()


def summarise(events: Sequence[Mapping[str, Any]], *, preset: str) -> RunSummary:
    """Fold a decoded event stream into one result.

    Pure: the same events always fold to the same summary. Conclusions come
    from the synthesis phase payload and cost from the terminal frame, because
    neither carries the other's fields.
    """
    synthesis = extract_synthesis_payload(list(events))
    terminal = extract_terminal_frame(events)

    errors = coerce_string_list(terminal.get("errors"))
    errors += [
        str(event.get("error", ""))
        for event in events
        if event.get("type") == "error" and event.get("error")
    ]

    tokens = terminal.get("total_tokens")
    if not isinstance(tokens, dict):
        tokens = {"input": 0, "output": 0, "total": 0}

    labels = synthesis.get("claim_labels")
    duration = _coerce_number(terminal.get("duration", terminal.get("duration_seconds")))
    cost = _coerce_number(terminal.get("total_cost_usd"))

    return RunSummary(
        preset=preset,
        method=extract_method(events),
        synthesis=synthesis.get("core_solution", ""),
        critical_insights=tuple(coerce_string_list(synthesis.get("critical_insights"))),
        open_questions=tuple(coerce_string_list(synthesis.get("open_questions"))),
        claim_labels=types.MappingProxyType(
            {k: str(v) for k, v in labels.items() if isinstance(k, str)}
            if isinstance(labels, dict)
            else {}
        ),
        action_blueprint=tuple(coerce_dict_list(synthesis.get("action_blueprint"))),
        citations=tuple(extract_citations(list(events))),
        models_used=tuple(extract_models_used(events)),
        total_tokens=types.MappingProxyType(dict(tokens)),
        total_cost_usd=cost,
        duration_seconds=duration,
        errors=tuple(dict.fromkeys(errors)),
    )
