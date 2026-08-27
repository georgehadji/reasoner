"""MCP tool definitions.

Each tool is a thin translation into the same application-layer calls the
HTTP agent routes make (api/routes/agent.py): idempotency via
application.services.idempotency, billing via run_metering.metered, results
via agent_results.summarise. No tool here re-implements any of that -- if a
behaviour is missing, it belongs in application/services/, not here.

No admin, key-management, billing-management, or GDPR tool is registered.
Deliberately: keep it that way. tests/test_mcp_tools.py pins the tool list.
"""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from reasoner.api.mcp.context import resolve_caller

# build_mcp_server() in api/mcp/__init__.py already verifies `mcp` is
# installed before importing this module, so these top-level imports are
# safe -- and required: with `from __future__ import annotations`, every
# type hint below is a lazily-evaluated string, and FastMCP's tool
# introspection resolves it from this module's globals. A name imported
# only inside register_tools() would not be visible to that resolution.


def _summary_to_dict(summary) -> dict[str, Any]:
    """RunSummary -> plain JSON-safe dict, matching the HTTP RunResult shape.

    Built field-by-field rather than via dataclasses.asdict(): that deep-copies
    every field, and copy.deepcopy() cannot handle the MappingProxyType
    RunSummary uses for claim_labels/total_tokens. A shallow dict()/list() is
    all a JSON-safe copy needs anyway. Mirrors api/routes/agent.py's own
    RunSummary -> RunResult conversion.
    """
    return {
        "preset": summary.preset,
        "method": summary.method,
        "errors": list(summary.errors),
        "total_tokens": dict(summary.total_tokens),
        "total_cost_usd": summary.total_cost_usd,
        "duration_seconds": summary.duration_seconds,
        "synthesis": summary.synthesis,
        "critical_insights": list(summary.critical_insights),
        "open_questions": list(summary.open_questions),
        "claim_labels": dict(summary.claim_labels),
        "premises": list(summary.premises),
        "action_blueprint": list(summary.action_blueprint),
        "citations": list(summary.citations),
        "models_used": list(summary.models_used),
    }


async def _run_and_bill(
    ctx,
    *,
    problem: str,
    preset: str,
    top_k: int,
    web_search: bool,
    source_type: str,
    client_run_id: str | None,
    interface: str,
) -> dict[str, Any]:
    """Shared body for reasoner_run and reasoner_followup's initial-turn case.

    Auth -> quota -> credits -> idempotency -> metered stream -> summary.
    Every stage reuses the exact function the HTTP agent routes call; see
    api/routes/agent.py::_metered_agent_stream for the HTTP-side twin.
    """
    from reasoner.api.dependencies import check_quota, require_credits, reserve_or_402
    from reasoner.api.run_observability import CreditSink, PrometheusObserver
    from reasoner.api.schemas import RunRequest
    from reasoner.api.streaming import run_stream_cached
    from reasoner.application.services.agent_results import summarise
    from reasoner.application.services.idempotency import register_run
    from reasoner.application.services.pipeline_service import PipelineService
    from reasoner.application.services.preset_service import PresetService
    from reasoner.application.services.run_metering import RunContext, metered

    user = await resolve_caller(ctx)
    await check_quota(user)
    await require_credits(user)

    reference_id = client_run_id or f"run:{uuid.uuid4()}"
    reserved_credits = await reserve_or_402(
        user_id=str(user.id), preset=preset, problem=problem, reference_id=reference_id,
    )
    await register_run(client_run_id)

    req = RunRequest(
        problem=problem,
        preset=preset,
        top_k=top_k,
        web_search=web_search,
        source_type=source_type,
        client_run_id=client_run_id,
    )
    run_ctx = RunContext(
        preset=preset,
        reference_id=reference_id,
        user_id=str(user.id),
        tier="free",
        interface=interface,
        reserved_credits=reserved_credits,
    )
    stream = run_stream_cached(
        req,
        user_id=str(user.id),
        preset_service=PresetService(),
        pipeline_service=PipelineService(),
    )

    events: list[dict] = []
    phases_seen = 0
    observer = PrometheusObserver(tier="free", preset=preset, interface=interface)
    async for chunk in metered(stream, run_ctx, CreditSink(), observer):
        if not chunk.startswith("data: "):
            continue
        import json

        try:
            event = json.loads(chunk[6:])
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") in ("phase_start", "phase_complete"):
            phases_seen += 1
            name = event.get("name") or f"phase {event.get('phase', '?')}"
            await ctx.report_progress(phases_seen, None, message=str(name))

    return _summary_to_dict(summarise(events, preset=preset))


def register_tools(mcp) -> None:
    """Attach every Reasoner tool to *mcp*. Called once, by build_mcp_server()."""

    @mcp.tool(
        annotations=ToolAnnotations(title="Run a reasoning pipeline"),
    )
    async def reasoner_run(
        problem: str,
        ctx: Context,
        preset: str = "auto-budget",
        top_k: int = 2,
        web_search: bool = False,
        source_type: str = "general",
        client_run_id: str | None = None,
    ) -> dict[str, Any]:
        """Delegate a judgement call to a panel of models from different labs.

        They generate competing answers, critique and score each other,
        stress-test the survivors, and return one synthesis in which every
        claim is labelled VERIFIED, HYPOTHESIS, or UNKNOWN. Takes 20-90
        seconds and costs real money. Use for decisions with more than one
        defensible answer; do not use for lookups, syntax, or summarisation
        -- call reasoner_gate first if you are unsure which this is.

        Args:
            problem: The decision or question, with the constraints that matter.
            preset: Preset id from reasoner_presets. Default auto-budget lets
                the router pick the method.
            top_k: How many candidate solutions survive critique.
            web_search: Force web grounding.
            source_type: Bias sources when searching: general, academic, or news.
            client_run_id: Idempotency key. Reusing one returns the original
                run's result instead of billing a second run.
        """
        return await _run_and_bill(
            ctx,
            problem=problem,
            preset=preset,
            top_k=top_k,
            web_search=web_search,
            source_type=source_type,
            client_run_id=client_run_id,
            interface="mcp",
        )

    @mcp.tool(
        annotations=ToolAnnotations(title="Continue a conversation", readOnlyHint=False),
    )
    async def reasoner_followup(
        question: str,
        conversation_id: str,
        previous_synthesis: str,
        ctx: Context,
        preset: str = "auto-budget",
    ) -> dict[str, Any]:
        """Ask a follow-up question with the prior conversation as context.

        Args:
            question: The new question.
            conversation_id: The id from a prior reasoner_run's response.
            previous_synthesis: The prior turn's synthesis text, so the model
                has continuity without replaying the full transcript.
            preset: Preset id; defaults to auto-budget.
        """
        import json

        from reasoner.api.dependencies import check_quota, require_credits, reserve_or_402
        from reasoner.api.run_observability import CreditSink, PrometheusObserver
        from reasoner.api.schemas import FollowupRequest
        from reasoner.api.streaming import run_followup_stream
        from reasoner.application.services.agent_results import summarise
        from reasoner.application.services.run_metering import RunContext, metered

        user = await resolve_caller(ctx)
        await check_quota(user)
        await require_credits(user)

        reference_id = f"followup:{uuid.uuid4()}"
        reserved_credits = await reserve_or_402(
            user_id=str(user.id), preset=preset, problem=question, reference_id=reference_id,
        )

        req = FollowupRequest(
            question=question,
            conversation_id=conversation_id,
            previous_synthesis=previous_synthesis,
            history=[],
            preset=preset,
        )
        run_ctx = RunContext(
            preset=preset,
            reference_id=reference_id,
            user_id=str(user.id),
            tier="free",
            interface="mcp",
            reserved_credits=reserved_credits,
        )
        stream = run_followup_stream(req, user_id=str(user.id))

        events: list[dict] = []
        phases_seen = 0
        observer = PrometheusObserver(tier="free", preset=preset, interface="mcp")
        async for chunk in metered(stream, run_ctx, CreditSink(), observer):
            if not chunk.startswith("data: "):
                continue
            try:
                event = json.loads(chunk[6:])
            except json.JSONDecodeError:
                continue
            events.append(event)
            if event.get("type") in ("phase_start", "phase_complete"):
                phases_seen += 1
                await ctx.report_progress(phases_seen, None, message=str(event.get("name", "")))

        return _summary_to_dict(summarise(events, preset=preset))

    @mcp.tool(
        annotations=ToolAnnotations(title="Preview routing", readOnlyHint=True),
    )
    async def reasoner_gate(problem: str, preset: str = "auto-budget") -> dict[str, Any]:
        """Preview how a problem would be routed, without running or paying for it.

        Returns action (direct/web_search/pipeline), method, confidence, and
        alternatives. Call this first when unsure whether reasoner_run is
        warranted -- it shares HyperGate's own cache, so a following
        reasoner_run on the same problem does not re-pay the routing cost.
        """
        from reasoner.application.services.gate_service import decide_route

        return await decide_route(problem, preset)

    @mcp.tool(
        annotations=ToolAnnotations(title="Estimate cost", readOnlyHint=True),
    )
    async def reasoner_estimate(problem: str, preset: str = "auto-budget") -> dict[str, Any]:
        """Estimate tokens, USD cost, and duration for a problem and preset.

        Does not run anything. Use to stay inside a budget before calling
        reasoner_run.
        """
        from reasoner.application.services.estimate_service import estimate_cost

        return await estimate_cost(problem, preset)

    @mcp.tool(
        annotations=ToolAnnotations(title="List presets", readOnlyHint=True),
    )
    async def reasoner_presets() -> dict[str, Any]:
        """List available presets with method, description, and primary model.

        Fetch once and cache; preset ids are data, not constants -- the
        catalogue changes independently of this tool's schema.
        """
        from reasoner.presets import PRESETS

        return {
            "presets": {
                preset_id: {
                    "name": preset.name,
                    "description": preset.description,
                    "primary_id": preset.primary_id,
                }
                for preset_id, preset in PRESETS.items()
            }
        }

    @mcp.tool(
        annotations=ToolAnnotations(title="Health check", readOnlyHint=True),
    )
    async def reasoner_health() -> dict[str, Any]:
        """Check that Reasoner is reachable and its dependencies are healthy.

        Public-detail view (no pool sizes, no Python version) -- same as an
        unauthenticated GET /api/health.
        """
        from reasoner.application.services.health_service import check_health

        return await check_health(is_admin=False)


__all__ = ["register_tools"]
