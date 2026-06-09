"""
Reasoner Pipeline - Output Renderer
Rich terminal display and JSON export, with method-specific layouts.

This module is now a thin compatibility shim over
``reasoner.application.services.renderers``.
"""

from __future__ import annotations

from reasoner.domain.pipeline_state import PipelineState

from reasoner.application.services.renderers import (
    RendererService,
    renderer_service,
    MethodType,
    _method_type,
)
from reasoner.application.services.renderers._shared import (
    console,
    _get_attr,
    _label_color,
    _duration,
    _render_stress,
    _render_action_blueprint,
    _render_errors,
    render_routing_table,
    _render_cost_summary,
    export_to_json,
    render_perspective_content,
)

# Re-export all renderer functions for backward compatibility
from reasoner.application.services.renderers._render_multi_perspective import _render_multi_perspective
from reasoner.application.services.renderers._render_debate import _render_debate
from reasoner.application.services.renderers._render_research import _render_research
from reasoner.application.services.renderers._render_jury import _render_jury
from reasoner.application.services.renderers._render_scientific import _render_scientific
from reasoner.application.services.renderers._render_socratic import _render_socratic
from reasoner.application.services.renderers._render_pre_mortem import _render_pre_mortem
from reasoner.application.services.renderers._render_bayesian import _render_bayesian
from reasoner.application.services.renderers._render_dialectical import _render_dialectical
from reasoner.application.services.renderers._render_analogical import _render_analogical
from reasoner.application.services.renderers._render_delphi import _render_delphi
from reasoner.application.services.renderers._render_cove import _render_cove
from reasoner.application.services.renderers._render_sot import _render_sot
from reasoner.application.services.renderers._render_tot import _render_tot
from reasoner.application.services.renderers._render_pot import _render_pot
from reasoner.application.services.renderers._render_self_discover import _render_self_discover


def render_pipeline_result(state: PipelineState) -> None:
    """Dispatch to the appropriate method-specific renderer."""
    method = _method_type(state.preset_name)
    renderer_service.render(method.value, state)
    _render_cost_summary(state)
