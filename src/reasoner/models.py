"""
Reasoner Pipeline — Core Data Models (backward-compat re-export shim).

WARNING: This module is a backward-compatibility shim.
New code should import directly from:
    reasoner.domain.core_types          — domain dataclasses
    reasoner.domain.pipeline_state      — PipelineState + containers

All existing imports continue to work through this shim.
"""

from pathlib import Path

# Re-export domain model types that were historically exposed via models.py
from reasoner.core.parsing import (  # noqa: F401
    ParseError,
    _parse_critique_scores,
    _parse_review_hypotheses,
    extract_json,
    extract_solution_prose,
    parse_evidence_bundles,
    strip_json_fences,
)
from reasoner.domain.core_types import (  # noqa: F401
    Assumption,
    CritiqueScore,
    Decomposition,
    FinalSolution,
    GenerationCandidate,
    MetaCognitiveAudit,
    ScenarioType,
    SolutionCandidate,
    SubProblem,
)
from reasoner.domain.models import (  # noqa: F401
    ClaimLabel,
    PerspectiveRegistry,
    PerspectiveType,
    TaskType,
)
from reasoner.domain.pipeline_state import (  # noqa: F401
    ConversationState,
    CostTrackingState,
    MethodState,
    PipelineCore,
    PipelineMeta,
    PipelineRemainder,
    PipelineState,
)


# Backward-compat: standalone load/save for auto-generated tests
# Moved to PipelineSerializationService (C3 refactor — I/O off domain object).
# Use lazy import to avoid circular chain:
#   models.py → pipeline_service → pipeline → application.pipeline → models.py
def load(path: "str | Path") -> "PipelineState":
    from reasoner.application.services.pipeline_service import PipelineSerializationService
    return PipelineSerializationService.load(path)

def save(state: "PipelineState", path: "str | Path") -> None:
    from reasoner.application.services.pipeline_service import PipelineSerializationService
    return PipelineSerializationService.save(state, path)
