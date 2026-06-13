"""Coding phase logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.core_types import SolutionCandidate
from reasoner.models import PerspectiveType
from reasoner.parsing import extract_json
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)


def _safe_extract_json(
    raw: str,
    services: WorkflowServices,
    state: PipelineState,
    phase: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse JSON from an LLM response, degrading gracefully on failure.

    Budget (and even premium) models often return raw code or markdown instead
    of the requested JSON structure. Rather than crashing the whole pipeline on
    a ParseError, log the failure and return a fallback that preserves the raw
    text so downstream phases can still surface the model's output.
    """
    try:
        return extract_json(raw)
    except Exception as exc:
        services.log("CODING", f"{phase}: JSON parse failed ({exc}); using raw fallback", state)
        result = dict(fallback) if fallback else {}
        result.setdefault("raw", raw)
        return result

async def run_coding_spec_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("CODING", "Analyzing coding request and producing spec...", state)
    raw, _ = await services.call_llm(
        role="coding_spec",
        system_prompt=phases.CODING_SPEC_SYSTEM,
        user_prompt=phases.coding_spec_prompt(state),
        state=state,
    )
    data = _safe_extract_json(raw, services, state, "spec")
    state.coding_state["spec"] = data
    state.coding_state["language"] = data.get("language", "")
    state.coding_state["framework"] = data.get("framework", "")
    files = data.get("files", [])
    if not files:
        # Spec parse failed or returned no files. Synthesize a single default
        # file spec so the generate phase can still produce code from the request.
        services.log("CODING", "spec produced no files; using single-file fallback spec", state)
        files = [{"path": "solution.py", "purpose": state.problem[:300]}]
    state.coding_state["files_to_generate"] = files

async def run_coding_generate_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("CODING", "Generating production code files in parallel...", state)
    files_to_generate: list[dict[str, Any]] = state.coding_state.get("files_to_generate", [])
    if not files_to_generate:
        state.errors.append("CODING: No files in spec — cannot generate.")
        return

    async def _generate_one(file_spec: dict[str, Any]) -> dict[str, Any]:
        raw, _ = await services.call_llm(
            role="coding_generate",
            system_prompt=phases.CODING_GENERATE_SYSTEM,
            user_prompt=phases.coding_generate_prompt(state, file_spec),
            state=state,
        )
        result = _safe_extract_json(raw, services, state, "generate")
        if not result.get("path"):
            result["path"] = file_spec.get("path", "unknown")
        if not result.get("content"):
            # On JSON-parse failure the raw model output is preserved under "raw";
            # use it as the file content rather than discarding the generated code.
            result["content"] = result.get("raw") or f"# Generation failed for {file_spec.get('path', '?')}"
        return result

    results = await asyncio.gather(*[_generate_one(f) for f in files_to_generate], return_exceptions=True)

    generated: list[dict[str, Any]] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            path = files_to_generate[i].get("path", f"file_{i}")
            generated.append({"path": path, "content": f"# Error: {res}", "language": "", "key_decisions": []})
        else:
            generated.append(res)

    state.coding_state["generated_files"] = generated

async def run_coding_review_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("CODING", "Running adversarial security and quality review...", state)
    if not state.coding_state.get("generated_files"):
        state.errors.append("CODING: No generated files to review.")
        return

    raw, _ = await services.call_llm(
        role="coding_review",
        system_prompt=phases.CODING_REVIEW_SYSTEM,
        user_prompt=phases.coding_review_prompt(state),
        state=state,
    )
    data = _safe_extract_json(raw, services, state, "review")
    state.coding_state["review"] = data

async def run_coding_tests_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("CODING", "Generating test suite...", state)
    raw, _ = await services.call_llm(
        role="coding_tests",
        system_prompt=phases.CODING_TESTS_SYSTEM,
        user_prompt=phases.coding_tests_prompt(state),
        state=state,
    )
    data = _safe_extract_json(raw, services, state, "tests")
    state.coding_state["tests"] = data

async def run_coding_assemble_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("CODING", "Assembling final production-ready output...", state)
    raw, _ = await services.call_llm(
        role="coding_assemble",
        system_prompt=phases.CODING_ASSEMBLE_SYSTEM,
        user_prompt=phases.coding_assemble_prompt(state),
        state=state,
    )
    data = _safe_extract_json(raw, services, state, "assemble")
    # If assemble fails to return structured files, fall back to the files already
    # produced by the generate phase so the final output is never empty.
    final_files = data.get("files") or state.coding_state.get("generated_files", [])
    state.coding_state["final_files"] = final_files
    state.coding_state["readme"] = data.get("readme", "")
    state.coding_state["fixes_applied"] = data.get("fixes_applied", [])
    state.coding_state["known_limitations"] = data.get("known_limitations", [])

    readme = state.coding_state.get("readme", "")
    files_summary = "\n\n".join(
        f"### {f['path']}\n```\n{f.get('content', '')[:1200]}\n```"
        for f in state.coding_state.get("final_files", [])
    )
    full_output = f"{readme}\n\n{files_summary}".strip()

    state.candidates.append(
        SolutionCandidate(
            perspective=PerspectiveType.CONSTRUCTIVE,
            content=full_output,
            key_insights=data.get("fixes_applied", []),
            model_used="",
        )
    )
