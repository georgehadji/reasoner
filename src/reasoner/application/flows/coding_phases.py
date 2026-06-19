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

    # Parse plan contract from decomposition output (code-as-harness #5)
    contract_data = data.get("contract", {})
    if contract_data:
        from reasoner.core.parsing import parse_plan_contract
        state.coding_state["contract"] = parse_plan_contract(contract_data)

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

    # Cap concurrent LLM calls to avoid rate-limit exhaustion on premium models.
    # 14 simultaneous calls to claude-sonnet reliably triggers 429s; 4 is safe.
    _sem = asyncio.Semaphore(4)

    async def _generate_one(file_spec: dict[str, Any]) -> dict[str, Any]:
        async with _sem:
            raw, _ = await services.call_llm(
                role="coding_generate",
                system_prompt=phases.CODING_GENERATE_SYSTEM,
                user_prompt=phases.coding_generate_prompt(state, file_spec),
                state=state,
            )
        result = _safe_extract_json(raw, services, state, "generate", fallback={"path": file_spec.get("path")})
        # Always enforce the expected path — never let the model override it.
        result["path"] = file_spec.get("path", result.get("path", "unknown"))
        if not result.get("content"):
            # On JSON-parse failure the raw model output is preserved under "raw";
            # use it as the file content rather than discarding the generated code.
            result["content"] = result.get("raw") or f"# Generation failed for {file_spec.get('path', '?')}"

        # Strip verbalized-sampling <think> tags from generated code
        if "<think>" in str(result.get("content", "")):
            from reasoner.core.parsing import strip_reasoning_tags
            result["content"] = strip_reasoning_tags(result["content"])
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

    # ── Contract validation (code-as-harness #5) ──
    # If the spec produced a plan contract with validation_commands,
    # run them through the code executor and feed results to evidence bundles.
    contract = state.coding_state.get("contract")
    if contract and contract.validation_commands and getattr(services, "code_executor", None):
        services.log("CODING", f"Validating contract — {len(contract.validation_commands)} commands", state)
        try:
            from reasoner.application.services.evidence_service import attach_execution_evidence
            # Concatenate validation commands as a single script for execution
            validation_script = "\n".join(contract.validation_commands)
            result = await services.code_executor.execute(validation_script)
            state.coding_state["contract_validation_result"] = result.__dict__
            if hasattr(state, 'final_solution') and state.final_solution:
                state.final_solution.evidence = attach_execution_evidence(
                    state.final_solution.evidence,
                    f"contract_validate:exit={result.exit_code}",
                )
            if not result.success:
                services.log("CODING", f"Contract validation failed: {result.summary}", state)
        except Exception as exc:
            services.log("CODING", f"Contract validation error: {exc}", state)

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
    data: dict = {}
    try:
        raw, _ = await services.call_llm(
            role="coding_assemble",
            system_prompt=phases.CODING_ASSEMBLE_SYSTEM,
            user_prompt=phases.coding_assemble_prompt(state),
            state=state,
        )
        data = _safe_extract_json(raw, services, state, "assemble")
    except Exception as exc:
        # Assemble is an enhancement pass; when the consolidated prompt is too large
        # or the LLM times out, fall back to the already-generated files directly.
        services.log("CODING", f"assemble LLM call failed ({exc}); using generated files as-is", state)
    # If assemble fails to return structured files, fall back to the files already
    # produced by the generate phase so the final output is never empty.
    final_files = data.get("files") or state.coding_state.get("generated_files", [])
    state.coding_state["final_files"] = final_files
    state.coding_state["readme"] = data.get("readme", "")
    state.coding_state["fixes_applied"] = data.get("fixes_applied", [])
    state.coding_state["known_limitations"] = data.get("known_limitations", [])

    readme = state.coding_state.get("readme", "")
    # Add a compact file index to candidates — NOT full file content.
    # Full file content can be thousands of tokens per file; including it
    # verbatim would cause the downstream synthesis phase to overflow the
    # context window (128k for claude-sonnet-4.6). The actual files are
    # stored in coding_state["final_files"] and don't need to be duplicated.
    files_index = "\n".join(
        f"- {f.get('path', '?')} ({len(f.get('content', '').splitlines())} lines)"
        for f in state.coding_state.get("final_files", [])
    )
    full_output = (
        f"{readme}\n\n## Generated Files\n{files_index}"
        if readme else f"## Generated Files\n{files_index}"
    ).strip()

    state.candidates.append(
        SolutionCandidate(
            perspective=PerspectiveType.CONSTRUCTIVE,
            content=full_output,
            key_insights=data.get("fixes_applied", []),
            model_used="",
        )
    )

    # Populate final_solution so the pipeline state is complete even without
    # a downstream synthesis phase (coding skips synthesis — see coding.py).
    from reasoner.domain.core_types import FinalSolution, MetaCognitiveAudit
    state.final_solution = FinalSolution(
        core_solution=full_output,
        critical_insights=data.get("fixes_applied", []),
        action_blueprint=[],
        open_questions=data.get("known_limitations", []),
        claim_labels={},
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption="",
            dominant_bias="",
            remaining_uncertainty="",
            assumption_failure_impact="",
            non_obvious_insight="",
        ),
        sources=[],
        layout_hints={"type": "code"},
    )
