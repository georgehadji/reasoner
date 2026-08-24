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
from reasoner.domain.pipeline_state import (
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
