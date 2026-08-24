"""
Reasoner Pipeline - Output Renderer
Rich terminal display and JSON export, with method-specific layouts.

This module is now a thin compatibility shim over
``reasoner.application.services.renderers``.
"""

from __future__ import annotations

from reasoner.application.services.renderers import (
    _method_type,
    renderer_service,
)

# Re-export all renderer functions for backward compatibility
from reasoner.application.services.renderers._shared import (
    _render_cost_summary,
)
from reasoner.domain.pipeline_state import PipelineState


def render_pipeline_result(state: PipelineState) -> None:
    """Dispatch to the appropriate method-specific renderer."""
    method = _method_type(state.preset_name)
    renderer_service.render(method.value, state)
    _render_cost_summary(state)
