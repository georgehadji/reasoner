"""Service for creating and managing ReasonerPipeline instances."""

from __future__ import annotations

import logging
from typing import Any

from reasoner.pipeline import ReasonerPipeline
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

class PipelineService:
    """Service to create ReasonerPipeline instances."""

    def create_pipeline(
        self,
        router: ProviderRouter,
        preset_name: str | None = None,
        top_k: int = 2,
        parallel_perspectives: bool = True,
        source_type: str = "general",
        domain: str | None = None,
        enhance_prompt: bool = False,
        complexity: str | None = None,
        batch_critique_jury: bool = False,
        initial_state: PipelineState | None = None,
    ) -> ReasonerPipeline:
        """Create a configured ReasonerPipeline instance."""
        return ReasonerPipeline(
            router=router,
            initial_state=initial_state,
            top_k=top_k,
            parallel_perspectives=parallel_perspectives,
            verbose=False,
            preset_name=preset_name,
            source_type=source_type,
            domain=domain,
            enhance_prompt=enhance_prompt,
            complexity=complexity,
            batch_critique_jury=batch_critique_jury,
        )
