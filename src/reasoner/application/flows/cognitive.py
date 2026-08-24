"""CoVE, SoT, ToT, PoT, and Self-Discover reasoning workflow strategies."""

from __future__ import annotations

from reasoner.application.flows.base import PhaseStep, WorkflowServices, WorkflowStrategy
from reasoner.application.flows.cognitive_phases import (
    run_cove_answer_phase,
    run_cove_draft_phase,
    run_cove_revise_phase,
    run_cove_verify_phase,
    run_pot_execute_phase,
    run_pot_generate_phase,
    run_pot_interpret_phase,
    run_sd_adapt_phase,
    run_sd_implement_phase,
    run_sd_select_phase,
    run_sot_assemble_phase,
    run_sot_skeleton_phase,
    run_sot_solve_phase,
    run_tot_backtrack_phase,
    run_tot_decompose_phase,
    run_tot_evaluate_phase,
    run_tot_generate_phase,
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5
from reasoner.domain.pipeline_state import PipelineState


class CoVEFlow(WorkflowStrategy):
    """Chain-of-Verification (CoVE) reasoning workflow."""
    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(2, "Draft Answer", run_cove_draft_phase, _ser_2),
            PhaseStep(3, "Verification", run_cove_verify_phase, _ser_3),
            PhaseStep(4, "Revised Answer", run_cove_answer_phase, _ser_4),
            PhaseStep(5, "Final Revision", run_cove_revise_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_5)
        ]
    async def execute(self, state: PipelineState, services: WorkflowServices) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state

class SoTFlow(WorkflowStrategy):
    """Skeleton-of-Thought (SoT) reasoning workflow."""
    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(2, "Skeleton", run_sot_skeleton_phase, _ser_2),
            PhaseStep(3, "Solve", run_sot_solve_phase, _ser_3),
            PhaseStep(4, "Assemble", run_sot_assemble_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5)
        ]
    async def execute(self, state: PipelineState, services: WorkflowServices) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state

class ToTFlow(WorkflowStrategy):
    """Tree-of-Thought (ToT) reasoning workflow."""
    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(2, "Decompose", run_tot_decompose_phase, _ser_2),
            PhaseStep(3, "Generate", run_tot_generate_phase, _ser_3),
            PhaseStep(4, "Evaluate", run_tot_evaluate_phase, _ser_4),
            PhaseStep(5, "Backtrack", run_tot_backtrack_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_5)
        ]
    async def execute(self, state: PipelineState, services: WorkflowServices) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state

class PoTFlow(WorkflowStrategy):
    """Program-of-Thought (PoT) reasoning workflow."""
    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(2, "Generate Code", run_pot_generate_phase, _ser_2),
            PhaseStep(3, "Execute", run_pot_execute_phase, _ser_3),
            PhaseStep(4, "Interpret", run_pot_interpret_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5)
        ]
    async def execute(self, state: PipelineState, services: WorkflowServices) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state

class SelfDiscoverFlow(WorkflowStrategy):
    """Self-Discover reasoning workflow."""
    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(2, "Select Modules", run_sd_select_phase, _ser_2),
            PhaseStep(3, "Adapt Modules", run_sd_adapt_phase, _ser_3),
            PhaseStep(4, "Implement", run_sd_implement_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5)
        ]
    async def execute(self, state: PipelineState, services: WorkflowServices) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state
