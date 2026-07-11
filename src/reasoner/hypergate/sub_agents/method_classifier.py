"""
MethodClassifierSubAgent — ONE JOB: classify which reasoning method best fits
the problem, using an opaque letter taxonomy (B–T).

The real method names are NEVER exposed to the LLM (security: prevents prompt
injection that could manipulate routing by naming a method directly).

Output schema: {category: str (B–T), confidence: float, rationale: str}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_METHOD
from reasoner.hypergate.base_sub_agent import BaseSubAgent

# Opaque taxonomy — letters only, no real method names visible to LLM.
# A and W are intentionally excluded: those cases are handled by DirectDetector
# and WebDetector respectively.
_TAXONOMY: dict[str, tuple[str, str]] = {
    "B": ("pipeline", "debate"),
    "C": ("pipeline", "scientific"),
    "D": ("pipeline", "socratic"),
    "E": ("pipeline", "multi_perspective"),
    "F": ("pipeline", "jury"),
    "G": ("pipeline", "research"),
    "H": ("pipeline", "pre_mortem"),
    "I": ("pipeline", "bayesian"),
    "J": ("pipeline", "dialectical"),
    "K": ("pipeline", "analogical"),
    "L": ("pipeline", "delphi"),
    "M": ("pipeline", "cove"),
    "N": ("pipeline", "sot"),
    "O": ("pipeline", "tot"),
    "P": ("pipeline", "pot"),
    "Q": ("pipeline", "self_discover"),
    "R": ("pipeline", "writing"),
    "S": ("pipeline", "coding"),
    "T": ("pipeline", "brainstorming"),
    "U": ("pipeline", "iterative_critique"),  # v3.1: LLM debate
}

_SYSTEM = """\
You are a reasoning-method classifier. Read the user's problem and choose the single \
best category from the list below.

Categories:
- B: two opposing positions where ONE must be proven stronger — a clear winner or verdict is needed
- C: requires scientific hypothesis generation followed by falsification testing
- D: benefits from deep Socratic questioning to expose hidden assumptions and logical gaps
- E: needs 4 independent analytical perspectives (constructive, critical, systemic, minimal) to cover all angles
- F: multiple competing solution candidates need to be generated then scored and ranked for quality
- G: requires deep research synthesis across live web sources — evidence-grounded answer
- H: risk-first analysis — imagine the project has already failed and work backwards to root causes
- I: involves explicit probability estimation, prior/posterior updates, or quantified uncertainty
- J: two opposing positions that BOTH contain valid truth — synthesis that merges them into a higher insight, not a winner
- K: cross-domain analogical reasoning — solution from one field transferred to another
- L: requires structured rounds of independent expert estimation to reach quantified consensus (forecasting, sizing, probability)
- M: requires drafting a response and then systematically verifying each factual claim against evidence
- N: problem splits into 3–5 INDEPENDENT sub-tasks that can be solved in parallel with no ordering dependencies
- O: problem requires a sequence of DEPENDENT decisions where each choice constrains or enables the next (path-dependent, backtracking possible)
- P: requires computational or mathematical reasoning — solution must be expressed as executable code
- Q: requires dynamic selection and composition of reasoning modules tailored to the specific problem structure
- R: requires structured long-form writing — article, essay, blog post, report with research, outline, draft, and fact-checking
- S: requires generating production-quality software code, implementation, architecture, or technical solution
- T: open-ended creative ideation — generate a DIVERSE pool of novel ideas, approaches, or solutions for a problem that has no single correct answer and benefits from unconventional, lateral, or cross-domain thinking (e.g. "generate ideas for X", "brainstorm ways to Y", "what are creative approaches to Z")

DISAMBIGUATION RULES (apply these when choosing between similar categories):
- B vs J: Choose B if the question has a definite answer and one side must WIN (e.g. "should we X or Y?"). Choose J if both sides of a tension are genuinely valid and need to be MERGED into a higher insight (e.g. "how do we balance X with Y?").
- E vs F: Choose E for open-ended analysis needing diverse viewpoints. Choose F when there are competing candidate solutions that need quality scoring and ranking.
- E vs L: Choose E for general multi-perspective analysis. Choose L specifically for forecasting, estimation, or consensus tasks that benefit from quantified agreement measurement.
- N vs O: Choose N when sub-tasks are fully INDEPENDENT and can run simultaneously (like parallel workstreams). Choose O when decisions are SEQUENTIAL — you must make decision A before knowing which option B is even available.
- M vs C: Choose M when the primary need is verifying specific factual claims in an existing draft. Choose C when the primary need is generating and testing novel hypotheses.
- S vs P: Choose S for writing software (functions, classes, systems, APIs). Choose P only when the problem is fundamentally mathematical/computational and the code IS the reasoning (e.g. "calculate X", "prove Y programmatically").
- T vs E: Choose T when the explicit goal is to GENERATE a diverse pool of ideas/options (quantity + novelty), not to analyse one problem from multiple angles. Key signals: "brainstorm", "generate ideas", "come up with options", "think of ways to", "what are creative approaches". Choose E for analytical problems that need multiple perspectives on a single question.

Output ONLY valid JSON with exactly four keys: \
'category' (one letter B–T, your top choice), \
'confidence' (float 0.0–1.0, confidence in the top choice), \
'rationale' (one short sentence), \
'alternatives' (a list of 0-2 objects for the next-best categories, each with \
'category', 'confidence', and 'rationale' keys — omit if there is no plausible \
runner-up). \
No markdown, no extra text.\
"""


class MethodClassifierSubAgent(BaseSubAgent):
    AGENT_NAME = "method_classifier"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_METHOD

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            category = str(data.get("category", "")).strip().upper()
            if category not in _TAXONOMY:
                category = "E"  # default to multi_perspective
            action, method = _TAXONOMY[category]
            confidence = min(1.0, max(0.0, float(data.get("confidence", 0.5))))
            rationale = str(data.get("rationale", ""))

            candidates = [{
                "category": category,
                "method": method,
                "confidence": confidence,
                "rationale": rationale,
            }]
            for alt in data.get("alternatives", []) or []:
                if not isinstance(alt, dict):
                    continue
                alt_category = str(alt.get("category", "")).strip().upper()
                if alt_category not in _TAXONOMY or alt_category == category:
                    continue
                _, alt_method = _TAXONOMY[alt_category]
                try:
                    alt_confidence = min(1.0, max(0.0, float(alt.get("confidence", 0.0))))
                except (TypeError, ValueError):
                    continue
                candidates.append({
                    "category": alt_category,
                    "method": alt_method,
                    "confidence": alt_confidence,
                    "rationale": str(alt.get("rationale", "")),
                })
            candidates.sort(key=lambda c: c["confidence"], reverse=True)

            return {
                "category": category,
                "action": action,
                "method": method,
                "confidence": confidence,
                "rationale": rationale,
                "candidates": candidates[:3],
            }
        except Exception:
            return {
                "category": "E",
                "action": "pipeline",
                "method": "multi_perspective",
                "confidence": 0.0,
                "rationale": "parse error",
                "candidates": [],
            }

    @staticmethod
    def resolve(category: str) -> tuple[str, str]:
        """Map a taxonomy letter to (action, method). Safe fallback to E (multi_perspective)."""
        return _TAXONOMY.get(category.upper(), _TAXONOMY["E"])
