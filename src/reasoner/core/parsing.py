"""
Reasoner Pipeline - Response Parsing Utilities
Robust JSON extraction from LLM responses.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from reasoner.domain.core_types import EvidenceBundle, PlanContract

from reasoner.domain.core_types import CritiqueScore, ReviewHypothesis
from reasoner.models import PerspectiveRegistry
from reasoner.utils.json_safe import JSONDepthExceededError, safe_json_loads


class ParseError(Exception):
    """Raised when LLM response cannot be parsed into expected structure."""
    def __init__(self, message, original_content=None):
        super().__init__(message)
        self.original_content = original_content


def strip_perplexity_citations(text: str) -> str:
    """Remove Perplexity-style citation markers and source sections."""
    text = re.sub(r"\s*\[\d+\]", "", text)
    for header in ("Sources:", "Citations:"):
        idx = text.find(header)
        if idx != -1:
            text = text[:idx].rstrip()
    return text


# Known provider-injected artifacts that leak into LLM responses.
_PROVIDER_ARTIFACTS: tuple[str, ...] = (
    "Please sign in to continue your reasoning session",
    "Please sign in to continue",
    "Sign in to continue your session",
    "Your session has expired",
    "Rate limit exceeded. Please try again",
    "This content has been blocked",
    "I'm sorry, but I can't assist with that",
)


def strip_provider_artifacts(text: str) -> str:
    """Remove known provider-injected artifacts from LLM responses."""
    for artifact in _PROVIDER_ARTIFACTS:
        idx = text.find(artifact)
        if idx != -1:
            # Remove the artifact and everything after it (usually trailing junk)
            text = text[:idx].rstrip()
    return text


def strip_prose_preamble(text: str) -> str:
    """Remove leading prose before the first JSON object or array."""
    start = min(
        (text.find("{"), text.find("[")),
        default=-1,
        key=lambda x: float("inf") if x == -1 else x,
    )
    return text[start:] if start != -1 else text


def extract_json(text: str) -> dict[str, Any]:
    """
    Extract JSON object (dict) from LLM response.
    Raises ParseError if no object found.
    """
    if not text or not text.strip():
        return {}

    # 1. Strip markdown fences and any surrounding whitespace
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    # 2. Extract using core engine
    parsed = extract_json_any(text)

    # 3. Validate - if it's already a dict, it was successfully extracted
    if isinstance(parsed, dict):
        return parsed

    # If it's a list (which extract_json_any can return if the JSON root is an array),
    # treat it as a list of results wrapped in a "results" key to maintain dict-like behavior.
    if isinstance(parsed, list):
        return {"results": parsed}

    raise ParseError(
        f"Could not extract valid JSON object from response. "
        f"Parsed type: {type(parsed).__name__}. "
        f"First 200 chars: {text[:200]!r}"
    )


def extract_json_list(text: str) -> list[Any]:
    """
    Extract JSON array (list) from LLM response.
    Raises ParseError if no array found.
    """
    parsed = extract_json_any(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        # Graceful degradation: extract values from dict
        return list(parsed.values())

    raise ParseError(
        f"Could not extract valid JSON list from response. "
        f"First 200 chars: {text[:200]!r}"
    )


# Compiled once at module level (v3.4 — was re.compiled per call)
_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>")
_REASONING_TAG_RE = re.compile(r"<reasoning>[\s\S]*?</reasoning>")


def _strip_reasoning_tags(text: str) -> str:
    """Strip <think>...</think> and similar reasoning artifacts from LLM output.

    Models like Gemini 3.5 Flash, DeepSeek R1, and Qwen thinking-mode can leak
    chain-of-thought inside <think> tags even when JSON-only output is requested.
    """
    text = _THINK_TAG_RE.sub("", text)
    text = _REASONING_TAG_RE.sub("", text)
    return text.strip()


# Public alias for use by coding phases (verbalized sampling)
strip_reasoning_tags = _strip_reasoning_tags


def extract_json_any(text: str) -> Any:
    """
    Core extraction engine. Handles markdown fences, prose, and malformed JSON.
    Returns dict, list, or None.
    """
    # CRITICAL: Limit input length to prevent regex DoS (ReDoS) attacks
    MAX_INPUT_LENGTH = 100000
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]

    text = strip_perplexity_citations(text.strip())
    text = strip_provider_artifacts(text)
    text = _strip_reasoning_tags(text)
    text = strip_prose_preamble(text)
    if not text:
        return None

    # Strip markdown fences
    if text.startswith("```json"):
        text = text[7:].lstrip()
    elif text.startswith("```"):
        text = text[3:].lstrip()
    if text.rstrip().endswith("```"):
        text = text.rstrip()[:-3].rstrip()

    fence_patterns = [
        r"```json\s*\n([\s\S]*?)\n```",
        r"```\s*\n([\s\S]*?)\n```",
        r"```json\s*\n([\s\S]*?)```",
        r"```\s*\n([\s\S]*?)```",
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
    ]

    for pattern in fence_patterns:
        match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
        if match:
            extracted = _sanitize_json_escapes(_strip_trailing_commas(match.group(1).strip()))
            try:
                return safe_json_loads(extracted, max_depth=100)
            except (json.JSONDecodeError, JSONDepthExceededError):
                pass

    # Try direct parse
    try:
        return safe_json_loads(_sanitize_json_escapes(_strip_trailing_commas(text)), max_depth=100)
    except (json.JSONDecodeError, JSONDepthExceededError):
        pass

    # Try to extract partial JSON with just core_analysis if full parse fails
    # This helps with graceful degradation
    partial_match = re.search(r'"core_analysis"\s*:\s*"((?:[^"\\]|\\.)*?)"(?:,\s*"|\s*})', text, re.DOTALL)
    if partial_match:
        core_analysis = partial_match.group(1)
        insights_match = re.search(r'"key_insights"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        insights = []
        if insights_match:
            insights_str = insights_match.group(1)
            for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', insights_str):
                insights.append(m.group(1))
        return {
            "core_analysis": core_analysis,
            "key_insights": insights[:5],
        }

    # Find outermost structural boundaries
    start_obj = text.find("{")
    start_arr = text.find("[")

    # Always prefer objects over arrays — objects carry semantic meaning (keys)
    # while arrays are often incidental or decorative in LLM responses.
    if start_obj != -1:
        obj = _extract_balanced_structure(text, start_obj, "{", "}")
        if obj is not None:
            try:
                return safe_json_loads(_sanitize_json_escapes(_strip_trailing_commas(obj)), max_depth=100)
            except (json.JSONDecodeError, JSONDepthExceededError):
                pass

    # Fallback to array extraction only if no object found
    if start_arr != -1:
        arr = _extract_balanced_structure(text, start_arr, "[", "]")
        if arr is not None:
            try:
                return safe_json_loads(_sanitize_json_escapes(_strip_trailing_commas(arr)), max_depth=100)
            except (json.JSONDecodeError, JSONDepthExceededError):
                pass

    # Try to repair truncated JSON (token-limit cutoffs) before falling back
    repaired = _repair_truncated_json(text)
    if repaired:
        try:
            return safe_json_loads(_sanitize_json_escapes(_strip_trailing_commas(repaired)), max_depth=100)
        except (json.JSONDecodeError, JSONDepthExceededError):
            pass

    # Fallback for objects with unescaped quotes
    reconstructed = _extract_json_dict_fallback(text)
    if reconstructed:
        return reconstructed

    return None


def _sanitize_json_escapes(text: str) -> str:
    r"""Fix invalid escape sequences that LLMs emit inside JSON strings.

    Common invalid escapes:
      \\'  ->  '   (single quotes don't need escaping in JSON)
      \\0  ->  removed or \\u0000
      \\xNN -> \\u00NN (hex escapes are not valid in JSON)
    """
    # Fix \\' inside strings — JSON strings only need \" for quotes
    text = re.sub(r"(?<!\\)\\'", "'", text)
    # Fix \\0 (null byte escape — invalid in JSON)
    text = re.sub(r"(?<!\\)\\0", "", text)
    # Fix \\xNN hex escapes → \u00NN
    text = re.sub(r"(?<!\\)\\x([0-9a-fA-F]{2})", lambda m: f"\\u00{m.group(1).upper()}", text)
    return text


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing braces/brackets — LLMs emit these often."""
    # Match comma followed by optional whitespace and a closing brace/bracket
    return re.sub(r',\s*([}\]])', r'\1', text)


def _extract_balanced_structure(text: str, start: int, open_char: str, close_char: str) -> str | None:
    """Extract a balanced structure (object or array) starting at index *start*."""
    depth, in_str, escape = 0, False, False
    for i, ch in enumerate(text[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if not in_str:
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None



def _extract_json_dict_fallback(text: str) -> dict[str, Any] | None:
    """
    Tolerant fallback that extracts key-value pairs from malformed JSON
    objects (e.g., with unescaped quotes inside values).
    Returns a dict if anything was extracted, else None.
    """
    result: dict[str, Any] = {}
    # Find all quoted keys followed by a colon
    for key_match in re.finditer(r'"([^"]+)"\s*:\s*', text):
        key = key_match.group(1)
        start = key_match.end()
        if start >= len(text):
            continue

        if text[start] == '"':
            # String value — scan for closing quote that is followed by , or }
            val, _ = _extract_json_string_value(text, start)
            if val is not None:
                result[key] = val
        elif text[start] == '[':
            # Array value — balance brackets
            arr = _extract_json_array_value(text, start)
            if arr is not None:
                result[key] = arr
        elif text[start] == '{':
            # Nested object — too complex for fallback, skip
            continue
        else:
            # Bare value (number, bool, null) — read until delimiter
            end = start
            while end < len(text) and text[end] not in ',}':
                end += 1
            bare = text[start:end].strip()
            if bare == "true":
                result[key] = True
            elif bare == "false":
                result[key] = False
            elif bare == "null":
                result[key] = None
            else:
                try:
                    result[key] = int(bare)
                except ValueError:
                    try:
                        result[key] = float(bare)
                    except ValueError:
                        result[key] = bare
    return result if result else None


def _extract_json_string_value(text: str, start: int) -> tuple[str | None, int]:
    """
    Extract a JSON string value starting at *start* (which must be a quote).
    Tolerates unescaped quotes inside the value by only accepting a closing
    quote when it is followed by a structural delimiter (, } or ]).

    Returns (value, end_index) where end_index is the position AFTER the
    closing quote.  Returns (None, start) if no valid closing quote is found.
    """
    if start >= len(text) or text[start] != '"':
        return None, start
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            if not in_str:
                # Potential closing quote — check what follows
                j = i + 1
                while j < len(text) and text[j].isspace():
                    j += 1
                if j < len(text) and text[j] in ",}]":
                    return text[start + 1:i].replace('\\"', '"'), j
    return None, start


def _extract_json_array_value(text: str, start: int) -> list[Any] | None:
    """
    Extract a JSON array starting at *start* (which must be '[').
    Tolerates unescaped quotes inside string items.
    """
    if start >= len(text) or text[start] != '[':
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if not in_str:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    arr_text = text[start:i + 1]
                    return _parse_json_array_items(arr_text)
    return None


def _parse_json_array_items(arr_text: str) -> list[Any]:
    """Parse items from a JSON array string (assumes well-formed brackets)."""
    items: list[str] = []
    i = 1  # skip [
    while i < len(arr_text) - 1:
        while i < len(arr_text) and arr_text[i].isspace():
            i += 1
        if i >= len(arr_text):
            break
        if arr_text[i] == '"':
            item, end = _extract_json_string_value(arr_text, i)
            if item is not None:
                items.append(item)
                i = end
            else:
                break
        else:
            # Skip non-string items
            i += 1
        while i < len(arr_text) and arr_text[i].isspace():
            i += 1
        if i < len(arr_text) and arr_text[i] == ",":
            i += 1
    return [it for it in items if it]


def _is_structural_quote(text: str, i: int) -> bool:
    """Return True if the quote at *i* is a JSON structural delimiter."""
    # Check preceding non-whitespace character
    j = i - 1
    while j >= 0 and text[j].isspace():
        j -= 1
    if j >= 0 and text[j] in "{[,:":
        return True
    # Check following non-whitespace character
    k = i + 1
    while k < len(text) and text[k].isspace():
        k += 1
    if k < len(text) and text[k] in "}],:":
        return True
    return False


def _repair_json_quotes(text: str) -> str | None:
    """
    Repair unescaped double quotes inside JSON string values.

    Identifies every unescaped quote that is NOT a JSON structural delimiter
    and escapes them all in one pass, then tries to parse again.
    """
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Build a new string where every non-structural unescaped quote is escaped.
    result = []
    i = 0
    while i < len(text):
        if text[i] == '"':
            # Count preceding backslashes
            backslashes = 0
            j = i - 1
            while j >= 0 and text[j] == '\\':
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0 and not _is_structural_quote(text, i):
                result.append('\\"')
            else:
                result.append('"')
        else:
            result.append(text[i])
        i += 1

    repaired = "".join(result)
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        return None


def _repair_truncated_json(text: str) -> str | None:
    """
    Close unclosed strings/arrays/objects caused by token-limit truncation.
    Returns repaired string, or None if structure is unrecoverable.
    """
    stack: list[str] = []
    in_str, escape = False, False

    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            if in_str:
                in_str = False
            else:
                in_str = True
            continue
        if not in_str:
            if ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]" and stack and stack[-1] == ch:
                stack.pop()

    if not stack and not in_str:
        return None  # already balanced — not a truncation issue

    suffix = ""
    if in_str:
        # AGGRESSIVE REPAIR: If truncated mid-string, truncate back to the last
        # structural boundary that lies OUTSIDE of a string. We scan backwards
        # while tracking string state so commas/brackets inside strings don't
        # trick us into cutting the string in half.
        last_boundary = _last_structural_boundary(text)
        if last_boundary != -1:
            # If the boundary was an opening bracket or brace, keep it so we
            # can close it as empty.
            if text[last_boundary] in "[{":
                text = text[:last_boundary + 1]
            else:
                text = text[:last_boundary]
            # Re-calculate stack for the modified text
            stack = []
            for ch in text:
                if ch in "{[":
                    stack.append("}" if ch == "{" else "]")
                elif ch in "}]" and stack:
                    stack.pop()
        else:
            suffix += '"'  # fallback: just close it

    # Trim trailing incomplete items
    tail = text.rstrip()
    tail = re.sub(r',\s*$', "", tail)  # drop trailing comma
    # Drop incomplete key-value pairs (handles both after-comma and first-in-object cases)
    tail = re.sub(r'([,{])\s*"[^"]*"\s*:\s*$', r'\1', tail)

    closing = "".join(reversed(stack))
    suffix = suffix + closing
    return tail + suffix


def _last_structural_boundary(text: str) -> int:
    """
    Scan backwards through *text* and return the index of the last comma,
    opening brace, or opening bracket that is OUTSIDE of a JSON string.
    Returns -1 if no such boundary exists.
    """
    in_str, escape = False, False
    # We need to scan forwards to know string state at each position,
    # then look backwards for the last boundary outside a string.
    # Simpler: scan forwards, recording the last valid boundary position.
    last_boundary = -1
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if not in_str and ch in ",[{":
            last_boundary = i
    return last_boundary


def extract_solution_prose(text: str) -> str | None:
    """
    Extract [SOLUTION]...[/SOLUTION] prose block from synthesis response.
    
    Returns:
        - The stripped prose content if found and non-empty
        - None if marker is absent OR if content is empty/whitespace-only
          (old JSON format or malformed response)
    """
    match = re.search(r"\[SOLUTION\]\s*(.*?)\s*\[/SOLUTION\]", text, re.DOTALL)
    if not match:
        return None

    # CRITICAL FIX: Return None for empty/whitespace-only content
    # This allows callers to distinguish between "no solution" and "empty solution"
    content = match.group(1).strip()
    return content if content else None


def strip_json_fences(text: str) -> str:
    """Remove markdown JSON code fences and any raw JSON block from text."""
    # Remove fenced code blocks
    text = re.sub(r"```json\s*.*?\s*```", "", text, flags=re.DOTALL)
    text = re.sub(r"```\s*.*?\s*```", "", text, flags=re.DOTALL)
    # Remove inline backtick wrappers
    text = re.sub(r"`[^`]*`", "", text)
    # Clean up extra whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_float(value: Any, default: float = 0.0, min_val: float = 0.0, max_val: float = 10.0) -> float:
    """Safely coerce a value to float within bounds."""
    try:
        return max(min_val, min(max_val, float(value)))
    except (TypeError, ValueError):
        return default


def safe_list(value: Any) -> list[str]:
    """
    Safely coerce to list of strings.
    
    Handles:
    - list: Convert each item to string
    - str: Wrap in single-item list
    - dict: Extract values and convert to strings (preserves data)
    - None/other: Return empty list
    
    Note: Does not handle circular references in dict values.
    """
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        # CRITICAL FIX: Extract dict values instead of silently returning empty list
        # This preserves data when LLM returns dict instead of list
        try:
            return [str(v) for v in value.values()]
        except (Exception, RecursionError):
            # Handle edge cases like circular references or unconvertible values
            return []
    return []


def _parse_critique_scores(raw_scores: list[dict]) -> list[CritiqueScore]:
    """Safely build CritiqueScore objects from raw LLM output.

    CritiqueScore has six required fields with no defaults.  LLMs occasionally
    omit one; passing the dict directly via **s raises TypeError and empties
    state.scores for the entire run.  Additionally, `perspective` arrives as a
    plain string and must be coerced to the PerspectiveType enum.
    """
    # Defensive normalisation: if the LLM returned a keyed dict instead of a list,
    # coerce to list of values.  If the input is not iterable at all, return empty
    # so callers don't crash with "string indices must be integers" etc.
    if isinstance(raw_scores, dict):
        raw_scores = list(raw_scores.values())
    if not isinstance(raw_scores, list):
        import logging
        logging.getLogger(__name__).warning(
            "CritiqueScore input is not a list (%s) — skipping",
            type(raw_scores).__name__,
        )
        return []
    out: list[CritiqueScore] = []
    for s in raw_scores:
        try:
            out.append(CritiqueScore(
                perspective=PerspectiveRegistry.coerce(s["perspective"]),
                logical_consistency=float(s.get("logical_consistency") or 0),
                evidence_support=float(s.get("evidence_support") or 0),
                failure_resilience=float(s.get("failure_resilience") or 0),
                feasibility=float(s.get("feasibility") or 0),
                bias_flags=s.get("bias_flags") or [],
                steel_man=s.get("steel_man") or "",
                confidence_vs_accuracy_penalty=float(s.get("confidence_vs_accuracy_penalty") or 0),
            ))
        except (KeyError, ValueError, TypeError) as exc:
            import logging
            logging.getLogger(__name__).warning("Skipping malformed CritiqueScore entry: %s", exc)
    return out


_VALID_SEVERITIES = {"HIGH", "MED", "LOW"}


def _parse_review_hypotheses(raw_hypotheses: Any) -> list[ReviewHypothesis]:
    """Safely build ReviewHypothesis objects from VS-critique LLM output.

    Defensive in the same spirit as `_parse_critique_scores`: coerce a keyed
    dict to a list, tolerate missing fields via `.get()`, clamp probability to
    [0, 1], normalise severity, and skip malformed entries rather than emptying
    the whole list. Hypotheses are returned sorted by descending probability so
    downstream consumers (display, Phase-4 seeding) can take the top-N directly.
    """
    if isinstance(raw_hypotheses, dict):
        raw_hypotheses = list(raw_hypotheses.values())
    if not isinstance(raw_hypotheses, list):
        if raw_hypotheses:
            logger.warning(
                "ReviewHypothesis input is not a list (%s) — skipping",
                type(raw_hypotheses).__name__,
            )
        return []
    out: list[ReviewHypothesis] = []
    for h in raw_hypotheses:
        if not isinstance(h, dict):
            continue
        try:
            prob = float(h.get("probability") or 0.0)
            prob = max(0.0, min(1.0, prob))
            severity = str(h.get("severity") or "LOW").strip().upper()
            if severity not in _VALID_SEVERITIES:
                severity = "LOW"
            claim = str(h.get("claim") or "").strip()
            if not claim:
                continue  # a hypothesis with no claim carries no signal
            out.append(ReviewHypothesis(
                claim=claim,
                probability=prob,
                severity=severity,
                evidence_for=str(h.get("evidence_for") or ""),
                evidence_against=str(h.get("evidence_against") or ""),
                verification=str(h.get("verification") or ""),
                cost_if_wrong=str(h.get("cost_if_wrong") or ""),
            ))
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping malformed ReviewHypothesis entry: %s", exc)
    out.sort(key=lambda x: x.probability, reverse=True)
    return out


def parse_evidence_bundle(data: dict[str, Any]) -> EvidenceBundle:
    """Tolerantly parse an EvidenceBundle from raw {label, checks_run, ...} dict.

    Returns an all-default bundle on any parse failure (``--resume`` safe).
    """
    from reasoner.domain.core_types import EvidenceBundle

    try:
        return EvidenceBundle(
            label=str(data.get("label", "UNKNOWN")).upper(),
            checks_run=list(data.get("checks_run") or []),
            evidence_refs=list(data.get("evidence_refs") or []),
            untested=str(data.get("untested") or ""),
            residual_risk=str(data.get("residual_risk") or ""),
            source=str(data.get("source", "model")),
        )
    except (ValueError, TypeError) as exc:
        logger.warning("Skipping malformed EvidenceBundle entry: %s", exc)
        return EvidenceBundle()


def parse_plan_contract(data: dict[str, Any]) -> PlanContract:
    """Tolerantly parse a PlanContract from raw decomposition LLM output.

    Returns an all-default contract on any parse failure (``--resume`` safe).
    """
    from reasoner.domain.core_types import PlanContract

    try:
        return PlanContract(
            targets=[str(t) for t in (data.get("targets") or [])],
            invariants=[str(i) for i in (data.get("invariants") or [])],
            validation_commands=[
                str(c) for c in (data.get("validation_commands") or [])
            ],
            rollback_points=[str(r) for r in (data.get("rollback_points") or [])],
            risky_ops=[str(o) for o in (data.get("risky_ops") or [])],
            read_set=[str(s) for s in (data.get("read_set") or [])],
            write_set=[str(s) for s in (data.get("write_set") or [])],
        )
    except (ValueError, TypeError) as exc:
        logger.warning("Skipping malformed PlanContract: %s", exc)
        return PlanContract()


def parse_evidence_bundles(
    raw: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, EvidenceBundle]:
    """Parse a dict of {claim_text: bundle_dict} from synthesis LLM output.

    Accepts list[dict] (coerces to dict by index), dict, or None.
    Returns a dict keyed by claim text.
    """

    result: dict[str, EvidenceBundle] = {}

    if isinstance(raw, list):
        # List of {claim, label, checks_run, ...} — index by claim
        for item in raw:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim") or "").strip()
            if not claim:
                continue
            result[claim] = parse_evidence_bundle(item)
    elif isinstance(raw, dict):
        # {claim_text: bundle_dict}
        for claim, bundle_data in raw.items():
            if not isinstance(bundle_data, dict):
                continue
            result[str(claim)] = parse_evidence_bundle(bundle_data)
    return result
