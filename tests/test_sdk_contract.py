"""Contract tests protecting the client SDKs from silent backend drift.

The SDK in ``sdk/typescript`` is a second public contract. Nothing in the type
checker connects it to this codebase, so a renamed request field or a dropped
SSE key would ship green and break consumers at runtime. These tests close that
gap from the backend side:

* **HTTP surface** — a normalised digest of the OpenAPI schema for exactly the
  endpoints the SDK calls, snapshotted to ``sdk/contract/openapi-digest.json``.
* **SSE surface** — the event keys the SDK reads, declared in
  ``sdk/contract/events.json``. OpenAPI cannot describe a stream, so that file
  stands in for it and ``sdk/typescript/test/contract.test.ts`` asserts the
  other half.

When one of these fails, the backend change is not necessarily wrong — but the
SDK needs updating and its version bumping before release. Refresh the snapshot
with::

    UPDATE_SDK_CONTRACT=1 python -m pytest tests/test_sdk_contract.py
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = REPO_ROOT / "sdk" / "contract"
OPENAPI_SNAPSHOT = CONTRACT_DIR / "openapi-digest.json"
EVENTS_CONTRACT = CONTRACT_DIR / "events.json"
PIPELINE_EXECUTION = REPO_ROOT / "src" / "reasoner" / "api" / "execution" / "pipeline.py"

#: Endpoints the TypeScript SDK calls. Adding a method there adds a line here.
SDK_ENDPOINTS: list[tuple[str, str]] = [
    ("post", "/api/run"),
    ("post", "/api/run-followup"),
    ("post", "/api/estimate"),
    ("post", "/api/gate"),
    ("get", "/api/presets"),
    ("get", "/api/models"),
    ("get", "/api/health"),
    ("get", "/api/credits"),
    ("get", "/api/credits/ledger"),
    ("get", "/api/credits/pricing"),
]

_UPDATE = os.environ.get("UPDATE_SDK_CONTRACT") == "1"


# ── OpenAPI digest ──────────────────────────────────────────────────


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type_name(schema: dict[str, Any]) -> str:
    """Render a JSON-Schema node as a short, stable type string.

    Deliberately lossy: the digest exists to catch renamed, added, or removed
    fields, not to reproduce the schema. Keeping it coarse means unrelated
    validator tweaks do not churn the snapshot.
    """
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if "anyOf" in schema:
        return "|".join(sorted({_type_name(s) for s in schema["anyOf"]}))
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _type_name(schema["allOf"][0])

    kind = schema.get("type")
    if kind == "array":
        return f"array<{_type_name(schema.get('items', {}))}>"
    return kind or "any"


def _referenced_schemas(schema: dict[str, Any], found: set[str]) -> None:
    """Collect every component schema reachable from ``schema``."""
    if "$ref" in schema:
        found.add(_ref_name(schema["$ref"]))
    for key in ("anyOf", "allOf", "oneOf"):
        for sub in schema.get(key, []):
            _referenced_schemas(sub, found)
    if "items" in schema:
        _referenced_schemas(schema["items"], found)
    for sub in schema.get("properties", {}).values():
        _referenced_schemas(sub, found)


def _schema_digest(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "required": sorted(schema.get("required", [])),
        "additional_properties": schema.get("additionalProperties", True),
        "properties": {
            name: _type_name(prop) for name, prop in sorted(schema.get("properties", {}).items())
        },
    }


def build_openapi_digest(openapi: dict[str, Any]) -> dict[str, Any]:
    """Reduce the full OpenAPI document to just the SDK's contract surface."""
    paths = openapi.get("paths", {})
    components = openapi.get("components", {}).get("schemas", {})

    endpoints: dict[str, Any] = {}
    referenced: set[str] = set()

    for method, path in SDK_ENDPOINTS:
        operation = paths.get(path, {}).get(method)
        assert operation is not None, (
            f"{method.upper()} {path} is gone from the OpenAPI schema, but the "
            f"TypeScript SDK still calls it. Either restore the route or remove "
            f"the method from sdk/typescript/src/client.ts."
        )

        entry: dict[str, Any] = {"responses": sorted(operation.get("responses", {}))}

        body = operation.get("requestBody")
        if body:
            schema = body.get("content", {}).get("application/json", {}).get("schema", {})
            _referenced_schemas(schema, referenced)
            entry["request_schema"] = _type_name(schema)
            entry["request_required"] = body.get("required", False)

        params = operation.get("parameters", [])
        if params:
            entry["query"] = {
                p["name"]: _type_name(p.get("schema", {}))
                for p in sorted(params, key=lambda p: p["name"])
                if p.get("in") == "query"
            }

        endpoints[f"{method.upper()} {path}"] = entry

    # Pull in nested schemas (AttachmentRef and friends) until the set closes.
    resolved: dict[str, Any] = {}
    pending = set(referenced)
    while pending:
        name = pending.pop()
        schema = components.get(name)
        if schema is None or name in resolved:
            continue
        resolved[name] = _schema_digest(schema)
        nested: set[str] = set()
        _referenced_schemas(schema, nested)
        pending |= nested - resolved.keys()

    return {
        "$comment": (
            "Generated by tests/test_sdk_contract.py. Do not hand-edit. "
            "Refresh with UPDATE_SDK_CONTRACT=1 pytest tests/test_sdk_contract.py, "
            "and update sdk/typescript to match before releasing."
        ),
        "endpoints": endpoints,
        "schemas": dict(sorted(resolved.items())),
    }


@pytest.fixture(scope="module")
def openapi_digest() -> dict[str, Any]:
    """Build the digest from the live app.

    Importing ``reasoner.api`` costs roughly five minutes and a lot of memory,
    which is why every test using this fixture is marked ``slow``: under
    ``-n auto`` each xdist worker would otherwise pay that import separately,
    which is enough to exhaust memory. They also carry an explicit
    ``timeout(900)`` because pyproject sets a 120s per-test default that this
    setup would otherwise blow through. The SSE tests below deliberately avoid
    the app import and stay in the fast lane.
    """
    from reasoner.api import app

    return build_openapi_digest(app.openapi())


@pytest.mark.slow
@pytest.mark.timeout(900)
@pytest.mark.unit
def test_sdk_http_surface_matches_the_committed_snapshot(openapi_digest: dict[str, Any]) -> None:
    if _UPDATE:
        CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
        OPENAPI_SNAPSHOT.write_text(
            json.dumps(openapi_digest, indent=2) + "\n", encoding="utf-8"
        )
        pytest.skip("Snapshot refreshed — rerun without UPDATE_SDK_CONTRACT to verify.")

    assert OPENAPI_SNAPSHOT.exists(), (
        f"{OPENAPI_SNAPSHOT} is missing. Generate it with "
        f"UPDATE_SDK_CONTRACT=1 pytest tests/test_sdk_contract.py"
    )

    committed = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))

    assert openapi_digest["endpoints"] == committed["endpoints"], (
        "The HTTP surface the SDK depends on changed. Update sdk/typescript to "
        "match, bump its version, then refresh this snapshot with "
        "UPDATE_SDK_CONTRACT=1 pytest tests/test_sdk_contract.py"
    )
    assert openapi_digest["schemas"] == committed["schemas"], (
        "A request schema the SDK sends changed shape. Update the matching type "
        "in sdk/typescript/src/types.ts, then refresh this snapshot."
    )


@pytest.mark.slow
@pytest.mark.timeout(900)
@pytest.mark.unit
def test_run_request_still_accepts_the_fields_the_sdk_sends(
    openapi_digest: dict[str, Any],
) -> None:
    """Guard the specific fields the SDK's RunParams puts on the wire."""
    schema = openapi_digest["schemas"]["RunRequest"]
    sdk_fields = {
        "problem",
        "preset",
        "top_k",
        "sequential",
        "enhance_prompt",
        "expert",
        "web_search",
        "smart_search",
        "source_type",
        "domain",
        "no_cache",
        "force_pipeline",
        "attachments",
        "file_ids",
        "client_run_id",
    }
    missing = sdk_fields - schema["properties"].keys()
    assert not missing, (
        f"sdk/typescript/src/types.ts RunParams sends {sorted(missing)}, which "
        f"RunRequest no longer accepts. Because RunRequest sets extra='forbid', "
        f"every such field is a hard 422 for SDK users, not a silent no-op."
    )


@pytest.mark.slow
@pytest.mark.timeout(900)
@pytest.mark.unit
def test_run_request_forbids_extra_fields_so_typos_fail_loudly(
    openapi_digest: dict[str, Any],
) -> None:
    """The SDK relies on strictness: a misspelled option must 422, not vanish."""
    assert openapi_digest["schemas"]["RunRequest"]["additional_properties"] is False


# ── SSE frame contract ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def events_contract() -> dict[str, Any]:
    return json.loads(EVENTS_CONTRACT.read_text(encoding="utf-8"))


def _done_payload_keys() -> set[str]:
    """Read the literal keys of the terminal ``done`` frame from its source.

    The frame is built inline inside the streaming coroutine, which cannot be
    called without driving a whole pipeline, so the keys are read off the dict
    literal instead. If that literal is ever restructured this raises rather
    than silently passing — which is the intended outcome, since a restructured
    done frame is exactly the change that needs a human to check the SDK.
    """
    tree = ast.parse(PIPELINE_EXECUTION.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "done_payload" not in names:
            continue
        return {
            key.value
            for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }

    raise AssertionError(
        f"No `done_payload = {{...}}` dict literal found in {PIPELINE_EXECUTION}. "
        f"If the terminal SSE frame is now built differently, verify that "
        f"sdk/contract/events.json still describes it and update this test."
    )


@pytest.mark.unit
def test_done_frame_carries_every_key_the_sdk_reads(events_contract: dict[str, Any]) -> None:
    required = set(events_contract["required_frames"]["done"]["required_keys"])
    actual = _done_payload_keys()

    missing = required - actual
    assert not missing, (
        f"The terminal `done` SSE frame no longer emits {sorted(missing)}. "
        f"sdk/typescript reads these in summarise(); total_cost_usd in particular "
        f"is what the backend itself settles credits from. Update the SDK and "
        f"sdk/contract/events.json together."
    )


def _synthesis_payload() -> dict[str, Any]:
    """Run the real synthesis serializer over a minimal state."""
    from reasoner.application.services.serializers import _ser_synthesis

    final_solution = SimpleNamespace(
        core_solution="Migrate incrementally.",
        critical_insights=["The monolith is not the bottleneck."],
        action_blueprint=[
            {
                "step": "1",
                "action": "Extract billing",
                "time_horizon": "Q1",
                "go_criteria": "Deploys independently",
                "fallback": "Module boundary only",
            }
        ],
        open_questions=["What is the deploy cadence?"],
        claim_labels={"The pipeline is the bottleneck": "VERIFIED"},
        evidence={},
        layout_hints={},
        meta_audit={"most_dangerous_assumption": "Team has capacity"},
    )
    state = SimpleNamespace(
        final_solution=final_solution,
        phase_tokens={"5": {"input": 100, "output": 200}},
        cross_language_state={},
    )
    return _ser_synthesis(state)


@pytest.mark.unit
def test_synthesis_payload_carries_every_key_the_sdk_reads(
    events_contract: dict[str, Any],
) -> None:
    contract = events_contract["required_frames"]["phase_complete.synthesis"]
    payload = _synthesis_payload()

    missing = set(contract["required_keys"]) - payload.keys()
    assert not missing, (
        f"The synthesis phase payload no longer emits {sorted(missing)}. This is "
        f"where critical_insights and open_questions actually live — the done "
        f"frame has never carried them. Update sdk/typescript/src/client.ts "
        f"summarise() and sdk/contract/events.json together."
    )


@pytest.mark.unit
def test_claim_labels_is_a_mapping_not_a_list() -> None:
    """The SDK types claim_labels as Record<string, string>.

    The serializer builds it with a dict comprehension over ``.items()``, so a
    change to a list would make the SDK silently return an empty mapping rather
    than fail — worth pinning explicitly.
    """
    payload = _synthesis_payload()
    assert isinstance(payload["claim_labels"], dict)
    assert all(isinstance(v, str) for v in payload["claim_labels"].values())


@pytest.mark.unit
def test_action_blueprint_entries_keep_their_five_fields(
    events_contract: dict[str, Any],
) -> None:
    payload = _synthesis_payload()
    expected = set(events_contract["action_step_keys"])

    assert payload["action_blueprint"], "Serializer dropped a well-formed blueprint step."
    for entry in payload["action_blueprint"]:
        missing = expected - entry.keys()
        assert not missing, (
            f"Action blueprint entries lost {sorted(missing)}; "
            f"sdk/typescript ActionStep declares all five."
        )


@pytest.mark.unit
def test_sample_stream_matches_the_declared_required_keys(
    events_contract: dict[str, Any],
) -> None:
    """The fixture the TypeScript side consumes must satisfy its own contract."""
    stream = events_contract["sample_stream"]

    done = next(e for e in stream if e["type"] == "done")
    done_required = set(events_contract["required_frames"]["done"]["required_keys"])
    assert not done_required - done.keys()

    synthesis = next(
        e for e in stream if e["type"] == "phase_complete" and "core_solution" in e.get("data", {})
    )
    synth_required = set(
        events_contract["required_frames"]["phase_complete.synthesis"]["required_keys"]
    )
    assert not synth_required - synthesis["data"].keys()
