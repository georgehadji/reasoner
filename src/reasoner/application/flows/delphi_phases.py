"""Delphi phase logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.models import PipelineState
from reasoner.parsing import extract_json, ParseError
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

async def run_delphi_round1_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DELPHI", "Round 1: Independent expert estimates...", state)
    tasks = [
        services.call_llm(
            role=f"expert_{i+1}",
            system_prompt=phases.DELPHI_EXPERT_SYSTEM,
            user_prompt=phases.delphi_round1_prompt(state, expert_num=i+1), 
            state=state
        )
        for i in range(4)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    estimates = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            state.errors.append(f"Delphi: Expert {i+1} Round 1 failed: {result}")
            continue
        raw, _ = result
        try:
            data = extract_json(raw)
        except ParseError as e:
            state.errors.append(f"Delphi: Expert {i+1} Round 1 parse error: {e}")
            continue
        if not isinstance(data, dict):
            state.errors.append(f"Delphi: Expert {i+1} Round 1 returned non-dict, skipping.")
            continue
        data["expert_id"] = f"expert_{i+1}"
        estimates.append(data)
    state.delphi_state["round_1_estimates"] = estimates

async def run_delphi_aggregation_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Aggregate round 1 estimates: compute median, IQR, identify outlier."""
    services.log("DELPHI", "Aggregating expert estimates...", state)
    estimates = state.delphi_state.get("round_1_estimates", [])
    if not estimates:
        state.errors.append("Delphi: No estimates to aggregate.")
        return
    # Extract numeric values
    values = []
    for e in estimates:
        val = e.get("estimate_value")
        if isinstance(val, (int, float)):
            values.append(val)
    if len(values) >= 2:
        values_sorted = sorted(values)
        n = len(values_sorted)
        mid = n // 2
        median = (values_sorted[mid-1] + values_sorted[mid]) / 2 if n % 2 == 0 else float(values_sorted[mid])
        q1 = values_sorted[n//4] if n > 2 else values_sorted[0]
        q3 = values_sorted[3*n//4] if n > 2 else values_sorted[-1]
        iqr = q3 - q1
        # Identify outlier (furthest from median)
        outlier_id = None
        max_dist = -1.0
        for e in estimates:
            val = e.get("estimate_value")
            if isinstance(val, (int, float)):
                dist = abs(val - median)
                if dist > max_dist:
                    max_dist = dist
                    outlier_id = e.get("expert_id")
        state.delphi_state["aggregated_stats"] = {
            "median": median,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "outlier_expert": outlier_id,
            "outlier_distance": max_dist if max_dist >= 0 else None,
            "n_estimates": len(values),
        }
    else:
        # Fallback: use LLM to aggregate qualitative estimates
        raw, _ = await services.call_llm(
            role="synthesis",
            system_prompt=phases.DELPHI_AGGREGATION_SYSTEM,
            user_prompt=phases.delphi_aggregation_prompt(state), 
            state=state
        )
        data = extract_json(raw)
        state.delphi_state["aggregated_stats"] = data

async def run_delphi_round2_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DELPHI", "Round 2: Experts revise with anonymous aggregate...", state)
    estimates = state.delphi_state.get("round_1_estimates", [])
    # Iterate actual expert IDs to handle any R1 failures correctly
    expert_ids = [e.get("expert_id", f"expert_{i+1}") for i, e in enumerate(estimates)]
    tasks = [
        services.call_llm(
            role=eid,
            system_prompt=phases.DELPHI_REVISION_SYSTEM,
            user_prompt=phases.delphi_round2_prompt(state, expert_id=eid), 
            state=state
        )
        for eid in expert_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    revised = []
    for eid, result in zip(expert_ids, results):
        if isinstance(result, Exception):
            state.errors.append(f"Delphi: {eid} Round 2 failed: {result}")
            continue
        raw, _ = result
        try:
            data = extract_json(raw)
        except ParseError as e:
            state.errors.append(f"Delphi: {eid} Round 2 parse error: {e}")
            continue
        if not isinstance(data, dict):
            state.errors.append(f"Delphi: {eid} Round 2 returned non-dict, skipping.")
            continue
        data["expert_id"] = eid
        revised.append(data)
    state.delphi_state["round_2_estimates"] = revised

async def run_delphi_convergence_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DELPHI", "Checking convergence...", state)
    estimates = state.delphi_state.get("round_2_estimates", [])
    values = [e.get("revised_estimate") for e in estimates if isinstance(e.get("revised_estimate"), (int, float))]
    if len(values) >= 2:
        values_sorted = sorted(values)
        n = len(values_sorted)
        mid = n // 2
        median = (values_sorted[mid-1] + values_sorted[mid]) / 2 if n % 2 == 0 else float(values_sorted[mid])
        q1 = values_sorted[n//4] if n > 2 else values_sorted[0]
        q3 = values_sorted[3*n//4] if n > 2 else values_sorted[-1]
        iqr = q3 - q1
        # Converged if IQR < 20% of |median| (or median is 0 and IQR is 0)
        converged = (iqr / abs(median) < 0.2) if median != 0 else (iqr == 0)
        state.delphi_state["converged"] = converged
        state.delphi_state["consensus"] = {
            "median": median,
            "iqr": iqr,
            "converged": converged,
        }
    else:
        # Qualitative convergence via LLM
        raw, _ = await services.call_llm(
            role="synthesis",
            system_prompt=phases.DELPHI_CONVERGENCE_SYSTEM,
            user_prompt=phases.delphi_convergence_prompt(state), 
            state=state
        )
        data = extract_json(raw)
        state.delphi_state["converged"] = data.get("converged", False)
        state.delphi_state["consensus"] = data

async def run_delphi_dissent_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DELPHI", "Capturing minority dissent...", state)
    stats = state.delphi_state.get("aggregated_stats", {})
    outlier = stats.get("outlier_expert", "expert_1")
    # Map outlier string like "expert_2" to role
    role = outlier if outlier in ("expert_1", "expert_2", "expert_3", "expert_4") else "expert_1"
    raw, _ = await services.call_llm(
        role=role,
        system_prompt=phases.DELPHI_DISSENT_SYSTEM,
        user_prompt=phases.delphi_dissent_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.delphi_state["dissent"] = data
