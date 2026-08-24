"""CoVE, SoT, ToT, PoT, and Self-Discover phase logic."""

from __future__ import annotations

import asyncio
import logging

import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.domain.core_types import SolutionCandidate
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import PerspectiveType
from reasoner.parsing import extract_json

logger = logging.getLogger(__name__)

# --- CoVE (Chain-of-Verification) ---

async def run_cove_draft_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("COVE", "Drafting initial answer...", state)
    raw, _ = await services.call_llm(
        role="cove_draft",
        system_prompt=phases.COVE_DRAFT_SYSTEM,
        user_prompt=phases.cove_draft_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.cove_state["draft_answer"] = data.get("draft_answer", "")
    state.cove_state["claims"] = data.get("claims", [])

async def run_cove_verify_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("COVE", "Generating verification questions...", state)
    raw, _ = await services.call_llm(
        role="cove_verify",
        system_prompt=phases.COVE_VERIFY_SYSTEM,
        user_prompt=phases.cove_verify_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.cove_state["verification_questions"] = data.get("verification_questions", [])

async def run_cove_answer_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("COVE", "Answering verification questions independently...", state)
    raw, _ = await services.call_llm(
        role="cove_answer",
        system_prompt=phases.COVE_ANSWER_SYSTEM,
        user_prompt=phases.cove_answer_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.cove_state["verification_answers"] = data.get("answers", [])

async def run_cove_revise_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("COVE", "Revising answer based on verification...", state)
    raw, _ = await services.call_llm(
        role="cove_revise",
        system_prompt=phases.COVE_REVISE_SYSTEM,
        user_prompt=phases.cove_revise_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.cove_state["revised_answer"] = data.get("revised_answer", "")
    state.cove_state["changes_made"] = data.get("changes_made", [])
    state.cove_state["remaining_uncertainties"] = data.get("remaining_uncertainties", [])
    # Feed revised answer into candidates for synthesis
    state.candidates.append(SolutionCandidate(
        perspective=PerspectiveType.CONSTRUCTIVE,
        content=state.cove_state.get("revised_answer", ""),
        key_insights=state.cove_state.get("changes_made", []),
        model_used="unknown", # We don't have phase_models here, but it's okay
    ))

# --- SoT (Skeleton-of-Thought) ---

async def run_sot_skeleton_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SoT", "Generating problem skeleton...", state)
    raw, _ = await services.call_llm(
        role="sot_skeleton",
        system_prompt=phases.SOT_SKELETON_SYSTEM,
        user_prompt=phases.sot_skeleton_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.sot_state["sub_problems"] = data.get("sub_problems", [])

async def run_sot_solve_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SoT", "Solving sub-problems in parallel...", state)
    sub_problems = state.sot_state.get("sub_problems", [])
    if not sub_problems:
        state.errors.append("SoT: No sub-problems to solve.")
        return
    semaphore = asyncio.Semaphore(4)
    async def _solve_one(sp: dict) -> dict:
        async with semaphore:
            raw, _ = await services.call_llm(
                role="sot_solve",
                system_prompt=phases.SOT_SOLVE_SYSTEM,
                user_prompt=phases.sot_solve_prompt(state, sp),
                state=state
            )
            data = extract_json(raw)
            return {
                "sub_problem_id": sp.get("id", ""),
                "solution": data.get("solution", ""),
                "key_insights": data.get("key_insights", []),
                "assumptions": data.get("assumptions", []),
            }
    tasks = [_solve_one(sp) for sp in sub_problems]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    solutions = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            state.errors.append(f"SoT: Sub-problem {i+1} solve failed: {result}")
            continue
        solutions.append(result)
    state.sot_state["solutions"] = solutions

async def run_sot_assemble_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SoT", "Assembling sub-problem solutions...", state)
    raw, _ = await services.call_llm(
        role="sot_assemble",
        system_prompt=phases.SOT_ASSEMBLE_SYSTEM,
        user_prompt=phases.sot_assemble_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.sot_state["assembled_answer"] = data.get("assembled_answer", "")
    state.sot_state["transitions"] = data.get("transitions", [])
    state.sot_state["resolved_conflicts"] = data.get("resolved_conflicts", [])
    state.candidates.append(SolutionCandidate(
        perspective=PerspectiveType.CONSTRUCTIVE,
        content=state.sot_state.get("assembled_answer", ""),
        key_insights=state.sot_state.get("transitions", []),
        model_used="unknown",
    ))

# --- ToT (Tree-of-Thought) ---

async def run_tot_decompose_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("ToT", "Decomposing into decision points...", state)
    raw, _ = await services.call_llm(
        role="tot_decompose",
        system_prompt=phases.TOT_DECOMPOSE_SYSTEM,
        user_prompt=phases.tot_decompose_prompt(state),
        state=state
    )
    try:
        data = extract_json(raw)
    except Exception:
        services.log("ToT", "Decompose phase failed JSON extraction, retrying...", state)
        raw, _ = await services.call_llm(
            role="tot_decompose",
            system_prompt="You are an analytical assistant. You MUST produce a valid JSON object ONLY. Do not include introductory text or markdown. Output JSON ONLY.",
            user_prompt=f"Previous attempt failed JSON parsing. Please re-generate the JSON for: {phases.tot_decompose_prompt(state)}",
            state=state
        )
        data = extract_json(raw)
    state.tot_state["decision_points"] = data.get("decision_points", [])
    state.tot_state["current_path"] = []

async def run_tot_generate_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("ToT", "Generating candidate actions...", state)
    dps = state.tot_state.get("decision_points", [])
    if not dps:
        state.errors.append("ToT: No decision points to generate candidates for.")
        return
    current_dp = dps[len(state.tot_state.get("current_path", []))]
    raw, _ = await services.call_llm(
        role="tot_generate",
        system_prompt=phases.TOT_GENERATE_SYSTEM,
        user_prompt=phases.tot_generate_prompt(state, current_dp),
        state=state
    )
    try:
        data = extract_json(raw)
    except Exception:
        services.log("ToT", "Generate phase failed JSON extraction, retrying...", state)
        raw, _ = await services.call_llm(
            role="tot_generate",
            system_prompt="You are an analytical assistant. You MUST produce a valid JSON object ONLY. Do not include introductory text or markdown. Output JSON ONLY.",
            user_prompt=f"Previous attempt failed JSON parsing. Please re-generate the JSON for: {phases.tot_generate_prompt(state, current_dp)}",
            state=state
        )
        data = extract_json(raw)
    state.tot_state["current_candidates"] = data.get("candidates", [])

async def run_tot_evaluate_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("ToT", "Evaluating candidates...", state)
    candidates = state.tot_state.get("current_candidates", [])
    if not candidates:
        state.errors.append("ToT: No candidates to evaluate.")
        return
    raw, _ = await services.call_llm(
        role="tot_evaluate",
        system_prompt=phases.TOT_EVALUATE_SYSTEM,
        user_prompt=phases.tot_evaluate_prompt(state, candidates),
        state=state
    )
    try:
        data = extract_json(raw)
    except Exception:
        services.log("ToT", "Evaluate phase failed JSON extraction, retrying...", state)
        raw, _ = await services.call_llm(
            role="tot_evaluate",
            system_prompt="You are an analytical assistant. You MUST produce a valid JSON object ONLY. Do not include introductory text or markdown. Output JSON ONLY.",
            user_prompt=f"Previous attempt failed JSON parsing. Please re-generate the JSON for: {phases.tot_evaluate_prompt(state, candidates)}",
            state=state
        )
        data = extract_json(raw)
    state.tot_state["evaluations"] = data.get("evaluations", [])
    state.tot_state["best_candidate"] = data.get("best_candidate", "")
    best = data.get("best_candidate", "")
    if best:
        state.tot_state["current_path"].append(best)

async def run_tot_backtrack_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("ToT", "Backtracking / finalizing path...", state)
    raw, _ = await services.call_llm(
        role="tot_backtrack",
        system_prompt=phases.TOT_BACKTRACK_SYSTEM,
        user_prompt=phases.tot_backtrack_prompt(state),
        state=state
    )
    try:
        data = extract_json(raw)
    except Exception:
        services.log("ToT", "Backtrack phase failed JSON extraction, retrying...", state)
        raw, _ = await services.call_llm(
            role="tot_backtrack",
            system_prompt="You are an analytical assistant. You MUST produce a valid JSON object ONLY. Do not include introductory text or markdown. Output JSON ONLY.",
            user_prompt=f"Previous attempt failed JSON parsing. Please re-generate the JSON for: {phases.tot_backtrack_prompt(state)}",
            state=state
        )
        data = extract_json(raw)
    state.tot_state["backtrack_decision"] = data.get("decision", "terminate")
    state.tot_state["final_path"] = data.get("final_path", [])
    state.tot_state["tot_confidence"] = data.get("confidence", 0.0)
    path_text = " → ".join(state.tot_state.get("final_path", []))
    state.candidates.append(SolutionCandidate(
        perspective=PerspectiveType.CONSTRUCTIVE,
        content=f"Tree-of-Thoughts optimal path: {path_text}",
        key_insights=[f"Decision: {data.get('decision', 'terminate')}"],
        model_used="unknown",
    ))

# --- PoT (Program-of-Thought) ---

async def run_pot_generate_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PoT", "Generating executable code...", state)
    raw, _ = await services.call_llm(
        role="pot_generate",
        system_prompt=phases.POT_GENERATE_SYSTEM,
        user_prompt=phases.pot_generate_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.pot_state["code"] = data.get("code", "")
    state.pot_state["explanation"] = data.get("explanation", "")
    state.pot_state["expected_output_type"] = data.get("expected_output_type", "")

async def run_pot_execute_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PoT", "Executing generated code...", state)
    code = state.pot_state.get("code", "")
    if not code:
        state.errors.append("PoT: No code to execute.")
        state.pot_state["execution_success"] = False
        state.pot_state["execution_output"] = ""
        state.pot_state["execution_error"] = "No code was generated"
        return

    # Use real code executor if available, otherwise fall back to LLM simulation
    executor = getattr(services, "code_executor", None)
    if executor is not None:
        # Audit trail: record the attempt before dispatch, so it's captured
        # even if the executor hangs or the host is killed mid-run.
        from reasoner.application.services.event_emission_service import get_event_emitter
        _emitter = get_event_emitter()
        if _emitter:
            _emitter.emit("CODE_EXECUTION_REQUESTED", phase_name="pot_execute", language="python")

        result = await executor.execute(code)
        state.pot_state["execution_output"] = result.stdout
        state.pot_state["execution_success"] = result.success
        state.pot_state["execution_error"] = result.stderr
        state.pot_state["execution_exit_code"] = result.exit_code
        state.pot_state["execution_timed_out"] = result.timed_out
        state.pot_state["execution_truncated"] = result.truncated
        state.pot_state["execution_evidence_id"] = str(result.exit_code)  # simplified evidence link

        if not result.success:
            services.log("PoT", f"Execution failed: {result.summary}", state)
        else:
            services.log("PoT", f"Execution OK: {result.summary}", state)

        # Audit trail: record the outcome — rejected (AST guard / disabled /
        # unhealthy sandbox, never contains code or output) vs. completed
        # (ran, success or runtime failure).
        if _emitter:
            if result.blocked:
                _emitter.emit("CODE_EXECUTION_REJECTED",
                              phase_name="pot_execute",
                              blocked_reason=result.blocked_reason)
            else:
                _emitter.emit("CODE_EXECUTION_COMPLETED",
                              phase_name="pot_execute",
                              exit_code=result.exit_code,
                              success=result.success,
                              duration_ms=result.duration_ms,
                              policy_version=result.policy_version)

        # Link execution evidence to claims for #3 evidence bundles
        try:
            from reasoner.application.services.evidence_service import attach_execution_evidence
            if hasattr(state, 'final_solution') and state.final_solution:
                state.final_solution.evidence = attach_execution_evidence(
                    state.final_solution.evidence,
                    f"pot_exec:{result.exit_code}:{result.duration_ms}ms",
                )
        except Exception:
            pass
    else:
        # Fallback — use LLM to simulate execution (original path)
        services.log("PoT", "No code executor available; using LLM simulation.", state)
        raw, _ = await services.call_llm(
            role="pot_execute",
            system_prompt=phases.POT_EXECUTE_SYSTEM,
            user_prompt=phases.pot_execute_prompt(state),
            state=state
        )
        data = extract_json(raw)
        state.pot_state["execution_output"] = data.get("output", "")
        state.pot_state["execution_success"] = data.get("success", False)
        state.pot_state["execution_error"] = data.get("error", "")
        state.pot_state["intermediate_steps"] = data.get("intermediate_steps", [])

async def run_pot_interpret_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PoT", "Interpreting execution results...", state)
    if not state.pot_state.get("execution_success", False):
        services.log("PoT", "Skipping interpretation — execution did not succeed.", state)
        state.pot_state["interpretation"] = "Execution failed; no results to interpret."
        state.pot_state["computed_answer"] = ""
        state.pot_state["caveats"] = []
        return
    raw, _ = await services.call_llm(
        role="pot_interpret",
        system_prompt=phases.POT_INTERPRET_SYSTEM,
        user_prompt=phases.pot_interpret_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.pot_state["interpretation"] = data.get("interpretation", "")
    state.pot_state["computed_answer"] = data.get("answer", "")
    state.pot_state["caveats"] = data.get("caveats", [])
    state.candidates.append(SolutionCandidate(
        perspective=PerspectiveType.CONSTRUCTIVE,
        content=state.pot_state.get("computed_answer", ""),
        key_insights=state.pot_state.get("caveats", []),
        model_used="unknown",
    ))

# --- Self-Discover ---

async def run_sd_select_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SELF-DISCOVER", "Selecting reasoning modules...", state)
    raw, _ = await services.call_llm(
        role="sd_select",
        system_prompt=phases.SD_SELECT_SYSTEM,
        user_prompt=phases.sd_select_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.self_discover_state["selected_modules"] = data.get("selected_modules", [])
    state.self_discover_state["composition_strategy"] = data.get("composition_strategy", "")

async def run_sd_adapt_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SELF-DISCOVER", "Adapting modules to problem...", state)
    raw, _ = await services.call_llm(
        role="sd_adapt",
        system_prompt=phases.SD_ADAPT_SYSTEM,
        user_prompt=phases.sd_adapt_prompt(state),
        state=state
    )
    data = extract_json(raw)
    state.self_discover_state["adapted_modules"] = data.get("adapted_modules", [])

async def run_sd_implement_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SELF-DISCOVER", "Implementing adapted reasoning pipeline...", state)
    raw, model = await services.call_llm(
        role="sd_implement",
        system_prompt=phases.SD_IMPLEMENT_SYSTEM,
        user_prompt=phases.sd_implement_prompt(state),
        state=state
    )
    data = extract_json(raw)

    # Rescue loop
    if not data:
        services.log("SELF-DISCOVER", "Implement phase failed JSON extraction, retrying...", state)
        raw, model = await services.call_llm(
            role="sd_implement",
            system_prompt="You are an analytical assistant. You MUST produce a valid JSON object ONLY. Do not include introductory text or markdown. Output JSON ONLY.",
            user_prompt=f"Previous attempt failed JSON parsing. Please re-generate the JSON for: {phases.sd_implement_prompt(state)}",
            state=state
        )
        data = extract_json(raw)

    state.self_discover_state["module_outputs"] = data.get("module_outputs", [])
    state.self_discover_state["final_answer"] = data.get("final_answer", "")
    state.self_discover_state["module_attribution"] = data.get("module_attribution", {})
    state.candidates.append(SolutionCandidate(
        perspective=PerspectiveType.CONSTRUCTIVE,
        content=state.self_discover_state.get("final_answer", ""),
        key_insights=[m.get("output", "") for m in state.self_discover_state.get("module_outputs", []) if isinstance(m, dict)],
        model_used=model,
    ))
