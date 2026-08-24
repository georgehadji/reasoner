"""FeedbackRouter — classify execution failures and route to repair strategies.

Paper grounding: §3.4.2 (planning as contract formation), §5.2.2 feedback routing:
compiler errors → local syntax repair; test failures → behavioral diagnosis;
coverage gaps → test generation; inconsistent reviews → arbitration.

This generalizes the VS Phase-4 handoff pattern already in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FailureType(str, Enum):
    """Classification of execution failures from #1's CodeExecutorPort."""
    COMPILE_ERROR = "compile_error"
    TEST_FAILURE = "test_failure"
    COVERAGE_GAP = "coverage_gap"
    TIMEOUT = "timeout"
    RUNTIME_ERROR = "runtime_error"
    REVIEW_CONFLICT = "review_conflict"
    UNKNOWN = "unknown"


class RepairStrategy(str, Enum):
    """Repair paths available to the orchestrator."""
    LOCAL_SYNTAX_FIX = "local_syntax_fix"          # COMPILE_ERROR → fix locally
    BEHAVIORAL_DIAGNOSIS = "behavioral_diagnosis"   # TEST_FAILURE → re-decompose
    TEST_GENERATION = "test_generation"             # COVERAGE_GAP → generate tests
    ARBITRATION = "arbitration"                     # REVIEW_CONFLICT → tie-breaker
    RETRY = "retry"                                 # TIMEOUT → reduce scope + retry
    ESCALATE = "escalate"                           # unrecoverable


@dataclass
class FeedbackAction:
    """Result of routing a failure to a repair strategy."""
    failure_type: FailureType = FailureType.UNKNOWN
    strategy: RepairStrategy = RepairStrategy.ESCALATE
    context: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def is_escalation(self) -> bool:
        return self.strategy == RepairStrategy.ESCALATE


# Default routing table: failure_type → RepairStrategy
_DEFAULT_ROUTING: dict[FailureType, RepairStrategy] = {
    FailureType.COMPILE_ERROR: RepairStrategy.LOCAL_SYNTAX_FIX,
    FailureType.TEST_FAILURE: RepairStrategy.BEHAVIORAL_DIAGNOSIS,
    FailureType.COVERAGE_GAP: RepairStrategy.TEST_GENERATION,
    FailureType.TIMEOUT: RepairStrategy.RETRY,
    FailureType.RUNTIME_ERROR: RepairStrategy.BEHAVIORAL_DIAGNOSIS,
    FailureType.REVIEW_CONFLICT: RepairStrategy.ARBITRATION,
    FailureType.UNKNOWN: RepairStrategy.ESCALATE,
}


def classify_failure(
    exit_code: int,
    stderr: str,
    timed_out: bool = False,
    blocked: bool = False,
) -> FailureType:
    """Classify a CodeExecutorPort ExecutionResult into a FailureType.

    Args:
        exit_code: Process exit code.
        stderr: Stderr output (lowered for pattern matching).
        timed_out: Whether the execution timed out.
        blocked: Whether the AST guard blocked the code.

    Returns:
        FailureType enum value.
    """
    if blocked:
        return FailureType.COMPILE_ERROR
    if timed_out:
        return FailureType.TIMEOUT
    if exit_code == 0:
        return FailureType.UNKNOWN  # success is not a failure

    lowered = stderr.lower()

    # Compile/syntax errors
    if any(marker in lowered for marker in (
        "syntaxerror", "indentationerror", "nameerror",
        "typeerror", "valueerror", "attributeerror",
        "importerror", "modulenotfounderror",
    )):
        return FailureType.COMPILE_ERROR

    # Test failures
    if any(marker in lowered for marker in (
        "assertionerror", "assert", "failed", "test failed",
        "pytest", "unittest",
    )):
        return FailureType.TEST_FAILURE

    # Runtime errors
    if any(marker in lowered for marker in (
        "runtimeerror", "exception", "traceback",
        "keyerror", "indexerror", "zerodivisionerror",
    )):
        return FailureType.RUNTIME_ERROR

    return FailureType.UNKNOWN


def route_failure(
    failure_type: FailureType,
    context: str = "",
    custom_routing: dict[FailureType, RepairStrategy] | None = None,
) -> FeedbackAction:
    """Route a classified failure to the appropriate repair strategy.

    Args:
        failure_type: Classified failure type.
        context: Human-readable context about what failed.
        custom_routing: Optional override of the default routing table.

    Returns:
        FeedbackAction with the chosen strategy.
    """
    routing = custom_routing or _DEFAULT_ROUTING
    strategy = routing.get(failure_type, RepairStrategy.ESCALATE)

    return FeedbackAction(
        failure_type=failure_type,
        strategy=strategy,
        context=context,
    )
