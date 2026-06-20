"""Phase quality monitor — hybrid rule-based + LLM judge evaluation."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from reasoner.core.constants import (
    GATE_MAX_TOKENS,
    GATE_TEMPERATURE,
    get_quality_judge_model,
    get_quality_judge_threshold,
)
from reasoner.quality.criteria import PhaseQualityResult, evaluate_rules

if TYPE_CHECKING:
    from reasoner.infrastructure.llm.router import ProviderRouter
    from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

_JUDGE_TIMEOUT = 10.0

_JUDGE_SYSTEM = (
    "You are a strict quality evaluator for an AI reasoning pipeline. "
    "Evaluate the phase output against the given criteria and return ONLY valid JSON."
)

_JUDGE_PROMPT_TMPL = """\
Phase: {phase_name} (attempt {attempt})
Quality criteria: {criteria}
Phase output summary: {summary}
Rule-based failure reason: {rule_reason}

Rate this phase output on a scale of 0-10 where:
- 10 = Perfect, all criteria fully met
- 6-9 = Acceptable, most criteria met with minor issues
- 3-5 = Marginal, some criteria met but significant gaps
- 0-2 = Failed, criteria not met

Threshold for pass: {threshold}.
Return ONLY this JSON (no markdown, no explanation):
{{"score": <float 0-10>, "passed": <bool>, "reason": "<one sentence>", "suggestions": ["<fix1>", "<fix2>"]}}
"""

_PHASE_JUDGE_PROMPTS: dict[str, str] = {
    "Synthesis": """\
Phase: Synthesis (attempt {attempt})
Rule failure: {rule_reason}
Output: core_solution length={core_len} chars, critical_insights count={insight_count}

Evaluate synthesis quality on these dimensions:
1. Integration: Does core_solution ({core_len} chars) synthesize multiple perspectives or just repeat one?
2. Insights: Are the {insight_count} critical_insights genuinely novel vs. restating the problem?
3. Actionability: Would a reader be able to act on this output?

Score 0-10. Threshold for pass: {threshold}.
Return ONLY: {{"score": <float>, "passed": <bool>, "reason": "<sentence>", "suggestions": ["<fix1>"]}}
""",

    "Perspectives": """\
Phase: Perspectives (attempt {attempt})
Rule failure: {rule_reason}
Output: {cand_count} candidates, content lengths={cand_lengths}

Evaluate perspective diversity:
1. Are the {cand_count} perspectives meaningfully different from each other?
2. Do they cover distinct angles (constructive, critical, systemic, minimalist)?
3. Is content depth sufficient? (very short lengths suggest truncation or parse errors)

Score 0-10. Threshold for pass: {threshold}.
Return ONLY: {{"score": <float>, "passed": <bool>, "reason": "<sentence>", "suggestions": ["<fix1>"]}}
""",

    "Critique & Pruning": """\
Phase: Critique & Pruning (attempt {attempt})
Rule failure: {rule_reason}
Output: {score_count} scores, {top_count} top_candidates selected

Evaluate critique rigor:
1. Discrimination: Are scores spread across the 0-10 range, or clustered tightly? Tight clustering indicates weak differentiation.
2. Selection: Were top_candidates ({top_count}) selected based on their scores or arbitrarily?
3. Coverage: Is there at least one candidate clearly stronger than the others?

Score 0-10. Threshold for pass: {threshold}.
Return ONLY: {{"score": <float>, "passed": <bool>, "reason": "<sentence>", "suggestions": ["<fix1>"]}}
""",
}

_PHASE_CRITERIA: dict[str, str] = {
    "Classification":        "task_type must be non-null",
    "Decomposition":         "at least 1 sub-problem must be present",
    "Perspectives":          "at least 1 candidate with content > 50 chars",
    "Critique & Pruning":    "scores list non-empty, top_candidates non-empty, all scores 0-10",
    "Stress Testing":        "at least 1 result with survival_rate in [0, 1]",
    "Synthesis":             "final_solution non-null, core_solution > 100 chars",
    "Decompose Topic":       "subquestions list non-empty",
    "Retrieve Sources":      "retrieved_sources list non-empty",
    "Extract Claims (CoVE)": "factcheck_reviews non-empty",
    "Final Assembly":        "final_article length > 500 chars",
    "Humanize":              "humanized_article or final_article non-empty",
}

_PHASE_SUMMARIES: dict[str, str] = {
    "Classification":        "task_type={task_type}",
    "Decomposition":         "sub-problems={decomp_count}",
    "Perspectives":          "candidates={cand_count}, lengths={cand_lengths}",
    "Critique & Pruning":    "scores={score_count}, top_candidates={top_count}",
    "Stress Testing":        "stress_results={stress_count}",
    "Synthesis":             "core_solution_len={core_len}, insights={insight_count}",
    "Decompose Topic":       "subquestions={subq_count}",
    "Retrieve Sources":      "sources={src_count}",
    "Extract Claims (CoVE)": "reviews={review_count}",
    "Final Assembly":        "article_len={article_len}",
    "Humanize":              "humanized_len={hum_len}",
}


def _build_format_values(state: "PipelineState") -> dict:
    """Return all template substitution values derived from pipeline state."""
    ws = getattr(state, "writing_state", {}) or {}
    sol = getattr(state, "final_solution", None)
    return {
        "task_type":     getattr(state, "task_type", None),
        "decomp_count":  len(getattr(state, "decomposition", None) or []),
        "cand_count":    len(getattr(state, "candidates", []) or []),
        "cand_lengths":  [len(getattr(c, "content", "") or "") for c in (getattr(state, "candidates", []) or [])],
        "score_count":   len(getattr(state, "scores", []) or []),
        "top_count":     len(getattr(state, "top_candidates", []) or []),
        "stress_count":  len(getattr(state, "stress_results", []) or []),
        "core_len":      len(getattr(sol, "core_solution", "") or "") if sol else 0,
        "insight_count": len(getattr(sol, "critical_insights", []) or []) if sol else 0,
        "subq_count":    len(ws.get("subquestions", []) or []),
        "src_count":     len(ws.get("retrieved_sources", []) or []),
        "review_count":  len(ws.get("factcheck_reviews", []) or []),
        "article_len":   len(ws.get("final_article", "") or ""),
        "hum_len":       len(ws.get("humanized_article", "") or ""),
    }


def _build_summary(phase_name: str, values: dict) -> str:
    """Build a short text summary of phase output for the generic judge template."""
    try:
        template = _PHASE_SUMMARIES.get(phase_name, "phase={phase_name}")
        return template.format(phase_name=phase_name, **values)
    except Exception:
        return f"phase={phase_name}"


class PhaseMonitor:
    """Evaluates phase output quality using rule-based checks with LLM fallback."""

    def __init__(self, router: "ProviderRouter", preset_name: str = "") -> None:
        self._router = router
        self._judge_model = get_quality_judge_model(preset_name)
        self._threshold = get_quality_judge_threshold(preset_name)

    async def evaluate(
        self, phase_name: str, state: "PipelineState", attempt: int = 1
    ) -> PhaseQualityResult:
        result = evaluate_rules(phase_name, state)
        if result.passed:
            return result

        try:
            llm_result = await asyncio.wait_for(
                self._llm_judge(phase_name, state, result, attempt=attempt),
                timeout=_JUDGE_TIMEOUT,
            )
            return llm_result
        except asyncio.TimeoutError:
            logger.warning("LLM judge timed out for phase %r — using rule result", phase_name)
            return result
        except Exception as exc:
            logger.warning("LLM judge failed for phase %r: %s — using rule result", phase_name, exc)
            return result

    async def _llm_judge(
        self,
        phase_name: str,
        state: "PipelineState",
        rule_result: PhaseQualityResult,
        *,
        attempt: int = 1,
    ) -> PhaseQualityResult:
        from reasoner.infrastructure.llm.ports import Message

        values = _build_format_values(state)
        summary = _build_summary(phase_name, values)
        criteria = _PHASE_CRITERIA.get(phase_name, "phase output must be non-empty and well-formed")

        template = _PHASE_JUDGE_PROMPTS.get(phase_name, _JUDGE_PROMPT_TMPL)
        try:
            prompt = template.format(
                phase_name=phase_name,
                attempt=attempt,
                criteria=criteria,
                summary=summary,
                rule_reason=rule_result.reason,
                threshold=self._threshold,
                **values,
            )
        except KeyError as exc:
            logger.warning("Phase judge prompt missing key %s for %r — falling back to generic", exc, phase_name)
            prompt = _JUDGE_PROMPT_TMPL.format(
                phase_name=phase_name,
                attempt=attempt,
                criteria=criteria,
                summary=summary,
                rule_reason=rule_result.reason,
                threshold=self._threshold,
                **values,
            )

        messages = [Message(role="user", content=prompt)]
        response = await self._router.complete(
            model_id=self._judge_model,
            messages=messages,
            system=_JUDGE_SYSTEM,
            max_tokens=GATE_MAX_TOKENS,
            temperature=GATE_TEMPERATURE,
        )

        raw = (response.content or "").strip()
        parsed = _parse_judge_response(raw)
        if parsed is None:
            logger.warning("LLM judge returned unparseable output for %r: %r", phase_name, raw[:200])
            return rule_result

        score = float(parsed.get("score", 0.0))
        passed = bool(parsed.get("passed", score >= self._threshold))
        reason = str(parsed.get("reason", rule_result.reason))
        suggestions = list(parsed.get("suggestions", rule_result.suggestions))

        return PhaseQualityResult(
            passed=passed,
            score=score,
            reason=reason,
            suggestions=suggestions,
        )


def _parse_judge_response(raw: str) -> dict | None:
    """Extract JSON from LLM judge response, tolerating markdown fences."""
    text = raw
    if "```" in text:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                text = stripped
                break
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                text = text[start:end]

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "score" in data:
            return data
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            data = json.loads(raw[start:end])
            if isinstance(data, dict) and "score" in data:
                return data
        except json.JSONDecodeError:
            pass

    return None
