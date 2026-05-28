"""Verbalized Sampling primitives — generation, parsing, normalization, sampling."""
from __future__ import annotations

import json
import random
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from reasoner.reasoner_vs_constants import (
    VS_K_GENERATION,
    VS_PARSE_MAX_RETRIES,
)


class VSMode(str, Enum):
    STANDARD = "standard"
    TAIL = "tail"
    COT = "cot"


class VSCandidate(BaseModel):
    text: str = Field(..., min_length=1)
    probability: float = Field(..., ge=0.0, le=1.0)


class VSResult(BaseModel):
    candidates: list[VSCandidate]
    mode: VSMode

    @field_validator("candidates")
    @classmethod
    def normalize_and_check(cls, v: list[VSCandidate]) -> list[VSCandidate]:
        total = sum(c.probability for c in v)
        if total == 0:
            n = len(v)
            return [VSCandidate(text=c.text, probability=1.0 / n) for c in v]
        if abs(total - 1.0) > 0.01:
            return [VSCandidate(text=c.text, probability=c.probability / total) for c in v]
        return v


def build_vs_prompt(query: str, mode: VSMode, k: int | None = None) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt). No string literals — all from constants."""
    _k = k if k is not None else VS_K_GENERATION
    system = f"Generate exactly {_k} diverse candidate answers for the query."
    if mode == VSMode.TAIL:
        system += " Include unconventional or tail-distribution candidates."
    elif mode == VSMode.COT:
        system += " Show step-by-step reasoning for each candidate."
    user = (
        f"Query: {query}\n"
        f'Respond as JSON: {{"candidates": [{{"text": "...", "probability": 0.1}}]}}'
    )
    return system, user


def _strip_markdown_fences(raw: str) -> str:
    """Remove ```json ... ``` fences and surrounding whitespace."""
    text = re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    # Also handle generic ``` fences if json-specific didn't match
    text = re.sub(r"^```\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def _extract_json_block(text: str) -> str:
    """Find the outermost JSON object containing 'candidates'."""
    # Find all top-level JSON objects by scanning braces
    objects: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth = 0
            start = i
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        objects.append(text[start : j + 1])
                        i = j
                        break
        i += 1

    for obj in objects:
        try:
            data = json.loads(obj)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "candidates" in data:
            return obj

    raise ValueError("No JSON candidate block found in VS response")


def parse_vs_response(raw: str) -> VSResult:
    """Strip fences, regex-extract JSON, validate structure."""
    text = _strip_markdown_fences(raw)
    json_block = _extract_json_block(text)
    data: dict[str, Any] = json.loads(json_block)
    candidates_data = data.get("candidates", [])
    if not isinstance(candidates_data, list):
        raise ValueError("'candidates' must be a list")
    candidates = [VSCandidate(text=str(c["text"]), probability=float(c["probability"])) for c in candidates_data]
    mode_str = data.get("mode", VSMode.STANDARD.value)
    mode = VSMode(mode_str)
    return VSResult(candidates=candidates, mode=mode)


def sample_from_vs(candidates: list[VSCandidate]) -> VSCandidate:
    """Probability-weighted sample."""
    if not candidates:
        raise ValueError("Cannot sample from empty candidate list")
    texts = [c.text for c in candidates]
    probs = [c.probability for c in candidates]
    idx = random.choices(range(len(texts)), weights=probs, k=1)[0]
    return candidates[idx]


def top_candidate(candidates: list[VSCandidate]) -> VSCandidate:
    """Deterministic; tie → first."""
    if not candidates:
        raise ValueError("Cannot select top candidate from empty list")
    return max(candidates, key=lambda c: (c.probability, -candidates.index(c)))


def compute_verbalized_entropy(candidates: list[VSCandidate]) -> float:
    """Shannon entropy of the candidate probability distribution."""
    import math

    probs = [c.probability for c in candidates if c.probability > 0]
    if not probs:
        return 0.0
    return -sum(p * math.log(p) for p in probs)
