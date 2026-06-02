"""Service for executing recovery paths on problematic candidates."""

from __future__ import annotations

import logging
from dataclasses import asdict

from reasoner.core.constants import TRUNCATION
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.core_types import (
    SolutionCandidate,
    GenerationCandidate,
)
from reasoner.parsing import ParseError, extract_json
from reasoner.application.flows.base import WorkflowServices
import reasoner.phases as phases

logger = logging.getLogger(__name__)

class RecoveryService:
    """Service providing recovery path execution."""

    @staticmethod
    async def run_recovery_path(
        state: PipelineState, 
        services: WorkflowServices, 
        candidate_to_verify: SolutionCandidate | GenerationCandidate
    ) -> None:
        """Executes a cross-verification path for a potentially problematic candidate."""
        cand_id = candidate_to_verify.perspective if isinstance(candidate_to_verify, SolutionCandidate) else candidate_to_verify.generator_id
        services.log("RECOVERY", f"Initiating recovery path for candidate: {cand_id}", state)
        
        try:
            raw_verification, _ = await services.call_llm(
                role="recovery_path",
                system_prompt=phases.CROSS_VERIFICATION_SYSTEM,
                user_prompt=phases.cross_verification_prompt(state, candidate_solution=asdict(candidate_to_verify)),
                max_tokens=1024, 
                state=state
            )
            verification_data = extract_json(raw_verification)
            if verification_data.get("verification_findings"):
                services.log("RECOVERY", f"Cross-verification found issues for candidate. Findings: {verification_data['verification_findings'][:TRUNCATION.MEMORY]}", state)
            else:
                services.log("RECOVERY", "Cross-verification found no issues.", state)
        except ParseError as e:
            services.log("RECOVERY", f"Recovery Path: Parse error during verification: {e}", state)
            state.errors.append(f"Recovery Path: Parse error during verification for candidate (id: {cand_id}): {str(e)}")
        except Exception as e:
            services.log("RECOVERY", f"Recovery Path: Verification failed: {e}", state)
            state.errors.append(f"Recovery Path: Verification failed for candidate (id: {cand_id}): {str(e)}")
        
        services.log("RECOVERY", "Recovery path complete.", state)
