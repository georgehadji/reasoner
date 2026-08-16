"""Function-calling tool definitions, projected from the request models.

A hand-written tool schema drifts the first time someone adds a field to
``RunRequest``. These are projected from that model's own JSON Schema, narrowed
by an explicit allowlist -- so a new field stays invisible to agents until
somebody deliberately exposes it, which is the right default for a public tool
surface.

The projection is pure and takes the schema as an argument rather than
importing it: ``RunRequest`` lives in the API layer, and this module sits under
it. The adapter passes ``RunRequest.model_json_schema()`` in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Fields an agent may set. Everything else on RunRequest -- routing overrides,
#: attachments, expert flags -- stays internal until it has a reason not to.
AGENT_FIELDS: tuple[str, ...] = (
    "problem",
    "preset",
    "top_k",
    "web_search",
    "source_type",
    "client_run_id",
)

#: Prose the model reads when deciding whether to reach for the tool. Kept here
#: rather than on the Pydantic model because it is written for an agent, not a
#: developer: cost and latency matter more than types.
_FIELD_DOCS: Mapping[str, str] = {
    "problem": (
        "The decision or question, including the constraints that matter. "
        "Decomposition can only split what you supply."
    ),
    "preset": (
        "Preset id from reasoner_presets, e.g. 'research-budget'. Omit for "
        "'auto-budget', which selects the reasoning method automatically."
    ),
    "top_k": "How many candidate solutions survive critique. Default 2.",
    "web_search": "Force web grounding. Usually unnecessary -- the router decides.",
    "source_type": "Bias sources when searching: 'general', 'academic', or 'news'.",
    "client_run_id": (
        "Idempotency key. Reusing one returns 409 instead of running -- and being "
        "charged -- twice. Send the same id when retrying a dropped run."
    ),
}


@dataclass(frozen=True)
class ToolDefinition:
    """One callable tool, in the shape both major schema dialects project from."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    read_only: bool = False
    endpoint: str = ""


def _project(request_schema: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """Narrow a Pydantic JSON Schema to *fields*, with agent-facing prose."""
    source = request_schema.get("properties", {})
    required = [f for f in request_schema.get("required", []) if f in fields]

    properties: dict[str, Any] = {}
    for name in fields:
        spec = source.get(name)
        if not isinstance(spec, Mapping):
            continue
        narrowed = {k: v for k, v in spec.items() if k not in ("title", "$ref", "allOf")}
        if name in _FIELD_DOCS:
            narrowed["description"] = _FIELD_DOCS[name]
        properties[name] = narrowed

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def build_tool_definitions(request_schema: Mapping[str, Any]) -> tuple[ToolDefinition, ...]:
    """Build the agent-facing tool set from ``RunRequest``'s JSON Schema."""
    run_input = _project(request_schema, AGENT_FIELDS)
    preflight_input = _project(request_schema, ("problem", "preset"))
    empty_input: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    return (
        ToolDefinition(
            name="reasoner_run_sync",
            description=(
                "Delegate a judgement call to a panel of models from different labs. They "
                "generate competing answers, critique and score each other, stress-test the "
                "survivors, and return one synthesis in which every claim is labelled "
                "VERIFIED, HYPOTHESIS, or UNKNOWN. Blocking: takes 20-90 seconds and costs "
                "real money. Use for decisions with more than one defensible answer; do not "
                "use for lookups, syntax, or summarisation."
            ),
            input_schema=run_input,
            endpoint="POST /api/agent/run/sync",
        ),
        ToolDefinition(
            name="reasoner_run",
            description=(
                "Same reasoning pipeline as reasoner_run_sync, streamed as Server-Sent "
                "Events. Prefer this only if you can consume a stream and want per-phase "
                "progress; otherwise use reasoner_run_sync."
            ),
            input_schema=run_input,
            endpoint="POST /api/agent/run",
        ),
        ToolDefinition(
            name="reasoner_gate",
            description=(
                "Preview how a problem would be routed -- direct answer, web search, or a "
                "named reasoning method -- without running it or spending anything. Cheap. "
                "Call this first when unsure whether a full run is warranted."
            ),
            input_schema=preflight_input,
            read_only=True,
            endpoint="POST /api/gate",
        ),
        ToolDefinition(
            name="reasoner_estimate",
            description=(
                "Estimate tokens, USD cost, and duration for a problem and preset without "
                "running it. Use to stay inside a budget before committing."
            ),
            input_schema=preflight_input,
            read_only=True,
            endpoint="POST /api/estimate",
        ),
        ToolDefinition(
            name="reasoner_presets",
            description=(
                "List available presets with their reasoning method, tier, and cost band. "
                "Fetch once and cache; preset names are data, not constants."
            ),
            input_schema=empty_input,
            read_only=True,
            endpoint="GET /api/presets",
        ),
        ToolDefinition(
            name="reasoner_health",
            description="Check that Reasoner is reachable and its dependencies are healthy.",
            input_schema=empty_input,
            read_only=True,
            endpoint="GET /api/health",
        ),
    )


def as_anthropic(definitions: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
    """Anthropic tool-use format."""
    return [
        {
            "name": d.name,
            "description": d.description,
            "input_schema": dict(d.input_schema),
        }
        for d in definitions
    ]


def as_openai(definitions: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
    """OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": d.name,
                "description": d.description,
                "parameters": dict(d.input_schema),
            },
        }
        for d in definitions
    ]


FORMATS = {"anthropic": as_anthropic, "openai": as_openai}


__all__ = [
    "AGENT_FIELDS",
    "FORMATS",
    "ToolDefinition",
    "as_anthropic",
    "as_openai",
    "build_tool_definitions",
]
