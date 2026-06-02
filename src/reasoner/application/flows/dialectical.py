"""Dialectical, Scientific, Socratic, Pre-Mortem, Bayesian, and Analogical reasoning workflow strategies."""

from __future__ import annotations

from typing import Any, List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowServices, WorkflowStrategy, PhaseStep
from reasoner.application.flows.dialectical_phases import (
    run_scientific_hypothesize_phase,
    run_scientific_test_phase,
    run_socratic_question_phase,
    run_socratic_answer_phase,
    run_pre_mortem_failure_phase,
    run_pre_mortem_backtrack_phase,
    run_pre_mortem_signals_phase,
    run_pre_mortem_redesign_phase,
    run_bayesian_priors_phase,
    run_bayesian_likelihood_phase,
    run_bayesian_posterior_phase,
    run_bayesian_sensitivity_phase,
    run_dialectical_thesis_phase,
    run_dialectical_antithesis_phase,
    run_dialectical_contradictions_phase,
    run_dialectical_aufhebung_phase,
    run_analogical_abstraction_phase,
    run_analogical_domain_search_phase,
    run_analogical_mapping_phase,
    run_analogical_transfer_phase
)
from reasoner.application.flows.perspective_phases import run_stress_test_phase
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5, _ser_synthesis

class ScientificFlow(WorkflowStrategy):
    """Scientific reasoning workflow."""
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Hypothesize", run_scientific_hypothesize_phase, _ser_2),
            PhaseStep(3, "Falsification Tests", run_scientific_test_phase, _ser_3),
            PhaseStep(4, "Stress Testing", run_stress_test_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(self, state: PipelineState, services: WorkflowServices, config: Any = None) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state

class SocraticFlow(WorkflowStrategy):
    """Socratic reasoning workflow."""
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Questioning", run_socratic_question_phase, _ser_2),
            PhaseStep(3, "Dialectic Answers", run_socratic_answer_phase, _ser_3),
            PhaseStep(4, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(self, state: PipelineState, services: WorkflowServices, config: Any = None) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state

class PreMortemFlow(WorkflowStrategy):
    """Pre-Mortem reasoning workflow."""
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Failure Narrative", run_pre_mortem_failure_phase, _ser_2),
            PhaseStep(3, "Root Cause Analysis", run_pre_mortem_backtrack_phase, _ser_3),
            PhaseStep(4, "Early Warning Signals", run_pre_mortem_signals_phase, _ser_4),
            PhaseStep(5, "Hardened Redesign", run_pre_mortem_redesign_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(self, state: PipelineState, services: WorkflowServices, config: Any = None) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state

class BayesianFlow(WorkflowStrategy):
    """Bayesian reasoning workflow."""
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Priors", run_bayesian_priors_phase, _ser_2),
            PhaseStep(3, "Likelihood Update", run_bayesian_likelihood_phase, _ser_3),
            PhaseStep(4, "Posterior Analysis", run_bayesian_posterior_phase, _ser_4),
            PhaseStep(5, "Sensitivity Analysis", run_bayesian_sensitivity_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(self, state: PipelineState, services: WorkflowServices, config: Any = None) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state

class DialecticalFlow(WorkflowStrategy):
    """Dialectical reasoning workflow."""
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Thesis", run_dialectical_thesis_phase, _ser_2),
            PhaseStep(3, "Antithesis", run_dialectical_antithesis_phase, _ser_3),
            PhaseStep(4, "Contradictions", run_dialectical_contradictions_phase, _ser_4),
            PhaseStep(5, "Aufhebung", run_dialectical_aufhebung_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(self, state: PipelineState, services: WorkflowServices, config: Any = None) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state

class AnalogicalFlow(WorkflowStrategy):
    """Analogical reasoning workflow."""
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Abstraction", run_analogical_abstraction_phase, _ser_2),
            PhaseStep(3, "Domain Search", run_analogical_domain_search_phase, _ser_3),
            PhaseStep(4, "Mapping", run_analogical_mapping_phase, _ser_4),
            PhaseStep(5, "Transfer", run_analogical_transfer_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(self, state: PipelineState, services: WorkflowServices, config: Any = None) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state
