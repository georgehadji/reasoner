"""Debate phase logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.core.constants import TRUNCATION
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json, _parse_critique_scores
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

async def run_debate_opening_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DEBATE", "Round 1: Opening Statements", state)
    
    # Extract stances from decomposition if available to create a meaningful debate
    stance_a = "In favor of the primary premise or proposing a proactive solution."
    stance_b = "Opposed to the primary premise or proposing a cautious/alternative approach."
    
    if state.decomposition:
         sub_problems = state.decomposition.get("sub_problems", []) if isinstance(state.decomposition, dict) else getattr(state.decomposition, "sub_problems", [])
         if sub_problems:
             # Use the first sub-problem to anchor the debate if nothing else is available
             stance_a = f"Propose a solution prioritizing: {sub_problems[0].description if hasattr(sub_problems[0], 'description') else sub_problems[0].get('description', '')}"
             if len(sub_problems) > 1:
                 stance_b = f"Propose an alternative solution prioritizing: {sub_problems[1].description if hasattr(sub_problems[1], 'description') else sub_problems[1].get('description', '')}"
             else:
                 stance_b = "Argue against the proactive solution, prioritizing caution and risk mitigation."

    async def _get_opening(side: str, stance: str):
        raw, _ = await services.call_llm(
            role="constructive" if side=="A" else "destructive", 
            system_prompt=phases.DEBATE_OPENING_SYSTEM, 
            user_prompt=phases.debate_opening_prompt(state, side, stance), 
            state=state
        )
        return extract_json(raw)
    
    results = await asyncio.gather(_get_opening("A", stance_a), _get_opening("B", stance_b), return_exceptions=True)
    statements = []
    for side, r in zip(["A", "B"], results):
        if isinstance(r, Exception):
            msg = f"Debate opening '{side}' failed: {r}"
            services.log("DEBATE", msg, state)
            state.errors.append(msg)
        else:
            statements.append(r)
    state.debate_rounds.append({"round": 1, "type": "opening", "statements": statements})

async def run_debate_rebuttal_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DEBATE", "Round 2: Rebuttals", state)
    opening_statements = state.debate_rounds[0].get('statements', []) if state.debate_rounds else []
    if len(opening_statements) < 2:
        msg = f"Debate rebuttal skipped: only {len(opening_statements)} opening statement(s) available"
        services.log("DEBATE", msg, state)
        state.errors.append(msg)
        return
        
    statement_a = opening_statements[0].get('content', '') if opening_statements[0] else ''
    statement_b = opening_statements[1].get('content', '') if len(opening_statements) > 1 and opening_statements[1] else ''
    
    if not statement_a or not statement_b:
        msg = "Debate rebuttal skipped: missing content in one or both opening statements."
        services.log("DEBATE", msg, state)
        state.errors.append(msg)
        return

    async def _get_rebuttal(side: str, opponent_statement: str):
        try:
            raw, _ = await services.call_llm(
                role="constructive" if side=="A" else "destructive", 
                system_prompt=phases.DEBATE_REBUTTAL_SYSTEM, 
                user_prompt=phases.debate_rebuttal_prompt(state, side, opponent_statement), 
                state=state
            )
            data = extract_json(raw)
            if "rebuttal_content" not in data:
                services.log("DEBATE", f"Warning: 'rebuttal_content' missing in Side {side}'s response.", state)
            return data
        except Exception as e:
            services.log("DEBATE", f"Error during rebuttal extraction for Side {side}: {e}", state)
            return None
    
    results = await asyncio.gather(_get_rebuttal("A", statement_b), _get_rebuttal("B", statement_a), return_exceptions=True)
    rebuttals = []
    for side, r in zip(["A", "B"], results):
        if isinstance(r, Exception):
            msg = f"Debate rebuttal '{side}' failed: {r}"
            services.log("DEBATE", msg, state)
            state.errors.append(msg)
        elif r is None:
            msg = f"Debate rebuttal '{side}' returned empty data."
            services.log("DEBATE", msg, state)
            state.errors.append(msg)
        else:
            r["side"] = side
            rebuttals.append(r)
    
    if rebuttals:
        state.debate_rounds.append({"round": 2, "type": "rebuttal", "rebuttals": rebuttals})
    else:
        services.log("DEBATE", "No valid rebuttals generated. Skipping appending round 2.", state)

async def run_debate_cross_examine_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DEBATE", "Running cross-examination...", state)
    side_a_claims = []
    side_b_claims = []
    for rd in state.debate_rounds:
        if rd.get("type") == "rebuttal":
            for rebuttal_entry in rd.get("rebuttals", []):
                if rebuttal_entry.get("side") == "A":
                    side_a_claims.append(rebuttal_entry.get("rebuttal_content", "")[:TRUNCATION.CONTENT])
                elif rebuttal_entry.get("side") == "B":
                    side_b_claims.append(rebuttal_entry.get("rebuttal_content", "")[:TRUNCATION.CONTENT])
    tasks = [
        services.call_llm(
            role="constructive",
            system_prompt=phases.DEBATE_CROSS_SYSTEM,
            user_prompt=phases.debate_cross_examine_prompt(state, "A", side_b_claims), 
            state=state
        ),
        services.call_llm(
            role="destructive",
            system_prompt=phases.DEBATE_CROSS_SYSTEM,
            user_prompt=phases.debate_cross_examine_prompt(state, "B", side_a_claims), 
            state=state
        ),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            services.log("DEBATE", f"Cross-examine error: {r}", state)
            continue
        raw, _ = r
        data = extract_json(raw)
        state.debate_rounds.append({
            "round": 3,
            "type": "cross_examination",
            "challenges": data,
        })

async def run_debate_judge_phase(state: PipelineState, services: WorkflowServices) -> None:
    if not state.debate_rounds:
        msg = "Debate judging skipped: no rounds in transcript"
        services.log("DEBATE", msg, state)
        state.errors.append(msg)
        return
    services.log("DEBATE", "Round 3: Judging", state)
    raw, _ = await services.call_llm(
        role="systemic", 
        system_prompt=phases.DEBATE_JUDGE_SYSTEM, 
        user_prompt=phases.debate_judge_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.scores = _parse_critique_scores(data.get("scores", []))
