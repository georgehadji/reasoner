"""Renderer strategy registry for Reasoner pipeline methods."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from reasoner.domain.pipeline_state import PipelineState

from ._shared import MethodType, _method_type


class RenderStrategy(Protocol):
    def __call__(self, state: PipelineState) -> None: ...


class RendererService:
    """Registry that maps method names to rendering strategies."""

    def __init__(self) -> None:
        self._strategies: dict[str, RenderStrategy] = {}

    def register(self, method: str, renderer: RenderStrategy) -> None:
        """Register a renderer for a method."""
        self._strategies[method] = renderer

    def render(self, method: str, state: PipelineState) -> None:
        """Render pipeline state using the strategy for the given method."""
        strategy = self._strategies.get(method, self._strategies.get("multi-perspective"))
        if strategy is not None:
            strategy(state)

    @property
    def methods(self) -> set[str]:
        """Return all registered method names."""
        return set(self._strategies.keys())


# Build and export the default service instance
from ._render_analogical import _render_analogical
from ._render_bayesian import _render_bayesian
from ._render_cove import _render_cove
from ._render_debate import _render_debate
from ._render_delphi import _render_delphi
from ._render_dialectical import _render_dialectical
from ._render_jury import _render_jury
from ._render_multi_perspective import _render_multi_perspective
from ._render_pot import _render_pot
from ._render_pre_mortem import _render_pre_mortem
from ._render_research import _render_research
from ._render_scientific import _render_scientific
from ._render_self_discover import _render_self_discover
from ._render_socratic import _render_socratic
from ._render_sot import _render_sot
from ._render_tot import _render_tot

renderer_service = RendererService()
renderer_service.register("multi-perspective", _render_multi_perspective)
renderer_service.register("debate", _render_debate)
renderer_service.register("research", _render_research)
renderer_service.register("jury", _render_jury)
renderer_service.register("scientific", _render_scientific)
renderer_service.register("socratic", _render_socratic)
renderer_service.register("pre-mortem", _render_pre_mortem)
renderer_service.register("bayesian", _render_bayesian)
renderer_service.register("dialectical", _render_dialectical)
renderer_service.register("analogical", _render_analogical)
renderer_service.register("delphi", _render_delphi)
renderer_service.register("cove", _render_cove)
renderer_service.register("sot", _render_sot)
renderer_service.register("tot", _render_tot)
renderer_service.register("pot", _render_pot)
renderer_service.register("self-discover", _render_self_discover)

__all__ = [
    "RendererService",
    "renderer_service",
    "MethodType",
    "_method_type",
]
