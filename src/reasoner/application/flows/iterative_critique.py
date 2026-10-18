"""Iterative Critique (LLM Debate) — Adversarial Refinement Strategy.

Generator-critic loop with convergence detection.
Implements "Adapt the interface, not the model" — runtime harness
adaptation via prompt orchestration instead of model fine-tuning.

Author: DeepSeek TUI — June 2026
"""

from __future__ import annotations

from reasoner.application.flows.base import PhaseStep, WorkflowServices, WorkflowStrategy
from reasoner.application.flows.iterative_critique_phases import (
    MAX_ROUNDS,
    AdversarialRound,
    check_convergence,
    run_critic_phase,
    run_generator_phase,
    run_synthesis_phase,
)
from reasoner.application.services.serializers import _ser_5
from reasoner.core.constants import IC_MAX_CONSECUTIVE_DEGRADED
from reasoner.core.degrade import degraded
from reasoner.domain.pipeline_state import PipelineState


class IterativeCritiqueFlow(WorkflowStrategy):
    """Adversarial debate: generator ↔ critic loop until convergence."""

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
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
                state.adversarial_convergence_round = round_num
                state.adversarial_convergence_reason = reason
                if reason == "critic_unavailable":
                    # The debate stopped; it did not converge. Say so in the
                    # state, the run's degradations and the event stream.
                    state.adversarial_converged = False
                    degraded(
                        "ic.critic",
                        None,
                        exc=RuntimeError("critic returned unusable output"),
                        state=state,
                        detail=(
                            f"{IC_MAX_CONSECUTIVE_DEGRADED} consecutive rounds, "
                            f"stopped at round {round_num}"
                        ),
                    )
                    state.pending_events.append({
                        "type": "phase_warning",
                        "message": (
                            "The critic stopped returning usable output; the debate "
                            "ended early and the answer was not independently reviewed."
                        ),
                    })
                    services.log(
                        "IC", f"Debate stopped at round {round_num}: critic unavailable", state
                    )
                else:
                    state.adversarial_converged = True
                    services.log("IC", f"Debate converged at round {round_num}", state)
                break
