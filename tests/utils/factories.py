"""Factory functions for creating test data objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from reasoner.infrastructure.llm.ports import Message, MessageRole, LLMConfig, LLMResponse
from reasoner.models import (
    PipelineState,
    SolutionCandidate,
    CritiqueScore,
    PerspectiveType,
    Decomposition,
    SubProblem,
    Assumption,
    ClaimLabel,
    StressTestResult,
    MetaCognitiveAudit,
    FinalSolution,
    CostTrackingState,
)
from reasoner.core.events.domain_events import EventType, make_event


def create_message(
    role: MessageRole = MessageRole.USER,
    content: str = "Hello, world!",
    metadata: dict[str, Any] | None = None,
) -> Message:
    return Message(role=role, content=content, metadata=metadata or {})


def create_llm_config(
    max_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.9,
) -> LLMConfig:
    return LLMConfig(
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )


def create_llm_response(
    content: str = "Mock LLM response",
    model_used: str = "test-model",
    tokens_prompt: int = 50,
    tokens_completion: int = 100,
    finish_reason: str = "stop",
) -> LLMResponse:
    return LLMResponse(
        content=content,
        model_used=model_used,
        tokens_prompt=tokens_prompt,
        tokens_completion=tokens_completion,
        finish_reason=finish_reason,
    )


def create_pipeline_state(
    problem: str = "What is the capital of France?",
    enhanced_problem: str = "",
    language: str = "English",
) -> PipelineState:
    return PipelineState(
        problem=problem,
        enhanced_problem=enhanced_problem or problem,
        language=language,
    )


def create_solution_candidate(
    perspective: PerspectiveType = PerspectiveType.ANALYTICAL,
    content: str = "Test solution",
    key_insights: list[str] | None = None,
    model_used: str = "test-model",
) -> SolutionCandidate:
    return SolutionCandidate(
        perspective=perspective,
        content=content,
        key_insights=key_insights or ["Insight 1"],
        model_used=model_used,
    )


def create_critique_score(
    perspective: PerspectiveType = PerspectiveType.ANALYTICAL,
    logical_consistency: float = 8.0,
    evidence_support: float = 7.5,
    failure_resilience: float = 7.0,
    feasibility: float = 8.5,
    bias_flags: list[str] | None = None,
    steel_man: str = "Best charitable interpretation",
    confidence_vs_accuracy_penalty: float = 0.0,
) -> CritiqueScore:
    return CritiqueScore(
        perspective=perspective,
        logical_consistency=logical_consistency,
        evidence_support=evidence_support,
        failure_resilience=failure_resilience,
        feasibility=feasibility,
        bias_flags=bias_flags or [],
        steel_man=steel_man,
        confidence_vs_accuracy_penalty=confidence_vs_accuracy_penalty,
    )


def create_decomposition(
    sub_problems: list[SubProblem] | None = None,
    assumptions: list[Assumption] | None = None,
    failure_modes: list[str] | None = None,
) -> Decomposition:
    return Decomposition(
        sub_problems=sub_problems or [
            SubProblem(
                id="sp-1",
                description="Sub-problem 1",
                inputs=["input1"],
                outputs=["output1"],
                constraints=["c1"],
            )
        ],
        assumptions=assumptions or [],
        failure_modes=failure_modes or ["Network timeout"],
    )


def create_final_solution(
    core_solution: str = "The answer is Paris.",
    critical_insights: list[str] | None = None,
) -> FinalSolution:
    return FinalSolution(
        core_solution=core_solution,
        critical_insights=critical_insights or ["Paris is the capital of France"],
        action_blueprint=[{"step": 1, "action": "Verify"}],
        open_questions=["What about other cities?"],
        claim_labels={"Paris is capital": ClaimLabel.VERIFIED},
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption="All sources agree",
            dominant_bias="Confirmation bias",
            remaining_uncertainty="Edge cases",
            assumption_failure_impact="Low",
            non_obvious_insight="Paris was not always the capital",
        ),
    )


def create_pipeline_started_event(
    aggregate_id: str = "test-pipeline-1",
    problem: str = "Test problem",
    preset: str = "test-preset",
) -> Any:
    return make_event(
        EventType.PIPELINE_STARTED,
        aggregate_id=aggregate_id,
        version=1,
        problem=problem,
        preset=preset,
        method="multi-perspective",
    )


def create_phase_completed_event(
    aggregate_id: str = "test-pipeline-1",
    phase_name: str = "classification",
    result: dict[str, Any] | None = None,
) -> Any:
    return make_event(
        EventType.PHASE_COMPLETED,
        aggregate_id=aggregate_id,
        version=2,
        phase_name=phase_name,
        result=result or {"task_type": "analytical"},
        tokens={"prompt": 100, "completion": 50},
        model_used="test-model",
        duration_seconds=1.5,
    )
