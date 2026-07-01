"""Iterative Critique (LLM Debate) — Adversarial Refinement Strategy.

Generator-critic loop with convergence detection.
Implements "Adapt the interface, not the model" — runtime harness
adaptation via prompt orchestration instead of model fine-tuning.

Author: DeepSeek TUI — June 2026
"""

from __future__ import annotations

from typing import List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.iterative_critique_phases import (
    run_generator_phase, run_critic_phase, run_synthesis_phase,
    AdversarialRound, check_convergence, MAX_ROUNDS,
)
from reasoner.application.services.serializers import _ser_5


class IterativeCritiqueFlow(WorkflowStrategy):
    """Adversarial debate: generator ↔ critic loop until convergence."""

    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(3, "Adversarial Debate", self._run_debate_loop, _ser_5, critical=False),
            PhaseStep(4, "Synthesis", run_synthesis_phase, _ser_5),
        ]

    async def _run_debate_loop(self, state: PipelineState, services: WorkflowServices) -> None:
        """Execute the generator-critic loop with convergence detection."""
        if not hasattr(state, 'adversarial_rounds') or state.adversarial_rounds is None:
            state.adversarial_rounds: list[AdversarialRound] = []

        answer = ""
        round_num = 0

        while round_num < MAX_ROUNDS:
            round_num += 1
            services.log("IC", f"--- Round {round_num}/{MAX_ROUNDS} ---", state)

            # Generator: produce or revise answer
            if round_num == 1:
                answer = await run_generator_phase(state, services, round_num=round_num)
            else:
                prev_round = state.adversarial_rounds[-1]
                answer = await run_generator_phase(
                    state, services,
                    previous_answer=prev_round.answer,
                    flaws=prev_round.flaws_identified,
                    round_num=round_num,
                )

            # Critic: evaluate the answer
            critic_round = await run_critic_phase(state, services, answer, round_num)
            state.adversarial_rounds.append(critic_round)

            # Check convergence
            converged, reason = check_convergence(state.adversarial_rounds)
            services.log("IC", f"Convergence: {converged} ({reason})", state)

            if converged:
                state.adversarial_converged = True
                state.adversarial_convergence_round = round_num
                state.adversarial_convergence_reason = reason
                services.log("IC", f"Debate converged at round {round_num}", state)
                break

    async def execute(self, state: PipelineState, services: WorkflowServices) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state
