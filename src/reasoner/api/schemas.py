"""Pydantic request/response schemas for the Reasoner API."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from reasoner.core.constants import (
    DEFAULT_PRESET,
    DEFAULT_SANITIZER_MAX_LENGTH,
    DEFAULT_SEARCH_RESULTS,
    DEFAULT_SEQUENTIAL,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_TOP_K,
    IMAGE_GEN_ALLOWED_ASPECT_RATIOS,
    IMAGE_GEN_ALLOWED_PRESETS,
    IMAGE_GEN_DEFAULT_ASPECT_RATIO,
    IMAGE_GEN_DEFAULT_PRESET,
    IMAGE_GEN_DEFAULT_RESOLUTION,
    IMAGE_GEN_IMAGE_COUNT,
    IMAGE_GEN_MAX_IMAGE_COUNT,
    TRUNCATION,
)
from reasoner.presets import is_valid_preset_name, resolve_preset_name


class SearchRequest(BaseModel):
    query: str
    source_type: str = DEFAULT_SOURCE_TYPE
    num_results: int = DEFAULT_SEARCH_RESULTS
    smart: bool = False

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Query cannot be empty")
        if len(v) > TRUNCATION.PROBLEM:
            raise ValueError(f"Query too long (max {TRUNCATION.PROBLEM} characters)")
        return v.strip()

    @field_validator("num_results")
    @classmethod
    def validate_num_results(cls, v: int) -> int:
        return max(1, min(v, 20))

    model_config = {"extra": "forbid"}


class AttachmentRef(BaseModel):
    file_id: str
    filename: str
    mime_type: str
    extracted_text: str
    size: int = 0

    model_config = {"extra": "forbid"}


class RunRequest(BaseModel):
    problem: str
    preset: str = DEFAULT_PRESET
    routing: dict[str, str] | None = None
    top_k: int = DEFAULT_TOP_K
    sequential: bool = DEFAULT_SEQUENTIAL
    no_cache: bool = False
    force_pipeline: bool = False
    enhance_prompt: bool = False
    expert: bool = False
    web_search: bool = False
    smart_search: bool = True
    source_type: str = DEFAULT_SOURCE_TYPE
    domain: str | None = None
    attachments: list[AttachmentRef] = []
    file_ids: list[str] = []
    client_run_id: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("problem")
    @classmethod
    def validate_problem(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Problem cannot be empty")
        if len(v) > DEFAULT_SANITIZER_MAX_LENGTH:
            raise ValueError(f"Problem too long (max {DEFAULT_SANITIZER_MAX_LENGTH} characters)")

        # SECURITY: Comprehensive input sanitization
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        if "\x00" in v:
            raise ValueError("Invalid characters in problem")

        v = re.sub(r"<script[^>]*>.*?</script>", "", v, flags=re.IGNORECASE | re.DOTALL)
        v = re.sub(r"<[^>]+>", "", v)

        try:
            import unicodedata

            v = unicodedata.normalize("NFKC", v)
        except ImportError:
            pass

        dangerous_patterns = [
            r"\{\{.*\}\}",
            r"<%.*%>",
            r"\$\{.*\}",
            r"eval\s*\(",
            r"exec\s*\(",
            r"__import__",
            r"subprocess",
            r"os\.system",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Problem contains disallowed content")

        if re.search(r"[^\w\s]{100,}", v):
            raise ValueError("Problem contains too many special characters")

        # SECURITY: Prompt-injection defense (layer 1)
        from reasoner.sanitization import sanitize_for_prompt

        v, _ = sanitize_for_prompt(v)
        v = v.strip()
        if not v:
            raise ValueError("Problem cannot be empty after sanitization")
        return v

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        if v.startswith("auto-") and v.split("-", 1)[1] in ("budget", "premium"):
            return v
        if not is_valid_preset_name(v):
            raise ValueError(f"Invalid preset: {v}")
        return resolve_preset_name(v)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        allowed = {"general", "academic", "social", "news", "code"}
        if v not in allowed:
            raise ValueError(f"Invalid source_type: {v}. Allowed: {allowed}")
        return v

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-.]*[a-zA-Z0-9]$", v):
            raise ValueError(f"Invalid domain format: {v}")
        if len(v) > 253:
            raise ValueError("Domain too long")
        return v.lower()


class FollowupRequest(BaseModel):
    question: str
    preset: str = DEFAULT_PRESET
    top_k: int = DEFAULT_TOP_K
    sequential: bool = DEFAULT_SEQUENTIAL
    enhance_prompt: bool = False
    expert: bool = False
    web_search: bool = False
    smart_search: bool = True
    conversation_id: str
    history: list[dict[str, str]]
    previous_synthesis: str
    agent_model: str | None = None
    attachments: list[AttachmentRef] = []
    file_ids: list[str] = []
    client_run_id: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        from reasoner.sanitization import sanitize_for_prompt

        v, _ = sanitize_for_prompt(v)
        return v

    # ── Prior-turn text is caller-supplied, not system-authored ──────────────
    # `previous_synthesis` and `history` arrive verbatim in the request body and
    # are rendered into every phase prompt by build_followup_context. Labelling
    # them "assistant turn" is a claim the caller makes, not one we can verify —
    # over MCP the caller is literally another agent.
    #
    # They use neutralize_for_replay, NOT the blocking sanitize_for_prompt used
    # for `question`. Blocking is right for a fresh instruction and wrong here:
    # an empty previous_synthesis is normal on the first follow-up, and this text
    # is usually Reasoner's own prose coming back, which can legitimately contain
    # a phrase like "System:". Rejecting those would be a self-inflicted denial
    # of service on our own output. The controls that actually matter on this
    # channel are the <<<EXTERNAL_CONTENT>>> wrapper and the propagation-
    # resistance rule in the system prompt.
    # See docs/MIND_VIRUS_MITIGATION.md §2.2.

    @field_validator("previous_synthesis")
    @classmethod
    def validate_previous_synthesis(cls, v: str) -> str:
        from reasoner.infrastructure.metrics import count_propagation_pattern
        from reasoner.sanitization import neutralize_for_replay

        v, warnings = neutralize_for_replay(v)
        if warnings:
            count_propagation_pattern("followup_synthesis", len(warnings))
        return v

    @field_validator("history")
    @classmethod
    def validate_history(cls, v: list[dict[str, str]]) -> list[dict[str, str]]:
        from reasoner.infrastructure.metrics import count_propagation_pattern
        from reasoner.sanitization import neutralize_for_replay

        cleaned: list[dict[str, str]] = []
        for turn in v:
            content, warnings = neutralize_for_replay(str(turn.get("content", "")))
            if warnings:
                count_propagation_pattern("followup_history", len(warnings))
            cleaned.append({**turn, "content": content})
        return cleaned


class GenerateImageRequest(BaseModel):
    """Request model for image generation."""

    prompt: str
    preset: str = IMAGE_GEN_DEFAULT_PRESET
    aspect_ratio: str = IMAGE_GEN_DEFAULT_ASPECT_RATIO
    resolution: str = IMAGE_GEN_DEFAULT_RESOLUTION
    enhance: bool = True
    preview_only: bool = False
    reference_images: list[str] = []
    # Unbounded here meant one request could fan out across the whole image
    # catalogue in parallel, each model a paid call. Asking for zero (or fewer)
    # images silently "succeeded" with no images, so the floor matters too.
    #
    # The default tracks IMAGE_GEN_IMAGE_COUNT rather than restating a number:
    # both tiers ship exactly that many primaries, one per lab, so a hardcoded
    # smaller default silently handed API callers a narrower cross-lab spread
    # than the UI gets and than the product claims.
    num_images: int = Field(
        default=IMAGE_GEN_IMAGE_COUNT, ge=1, le=IMAGE_GEN_MAX_IMAGE_COUNT
    )

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Prompt cannot be empty")
        if len(v) > 4000:
            # Enforce a hard limit to avoid request rejection downstream.
            v = v[:4000]
        return v

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, v: str) -> str:
        allowed = set(IMAGE_GEN_ALLOWED_PRESETS)
        if v not in allowed:
            raise ValueError(f"Invalid image generation preset: {v}. Allowed: {allowed}")
        return v

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, v: str) -> str:
        allowed = set(IMAGE_GEN_ALLOWED_ASPECT_RATIOS)
        if v not in allowed:
            raise ValueError(f"Invalid aspect ratio: {v}. Allowed: {allowed}")
        return v

    @field_validator("reference_images")
    @classmethod
    def validate_reference_images(cls, v: list[str]) -> list[str]:
        if len(v) > 4:
            raise ValueError("At most 4 reference images are allowed")
        for image in v:
            if not isinstance(image, str) or not image.startswith("data:image/"):
                raise ValueError("Reference images must be image data URLs")
        return v

    model_config = {"extra": "forbid"}


class ContextAnalysisRequest(BaseModel):
    """Request model for running pipeline with external context."""

    problem: str
    context: list[dict[str, Any]]
    method: str = "jury"
    preset: str = "jury-premium"
    top_k: int = 2
    domain: str | None = None

    @field_validator("problem")
    @classmethod
    def validate_problem(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Problem cannot be empty")
        return v

    @field_validator("context")
    @classmethod
    def validate_context_length(cls, v: list) -> list:
        if len(v) > 100:
            raise ValueError("Context list cannot exceed 100 items")
        return v

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("jury", "multi-perspective"):
            raise ValueError('Method must be "jury" or "multi-perspective"')
        return v

    model_config = {"extra": "forbid"}


class SuggestionRequestModel(BaseModel):
    query: str
    chat_history: list[list[str]] | None = None
    max_suggestions: int = 5

    model_config = {"extra": "forbid"}


class WeatherRequest(BaseModel):
    location: str

    model_config = {"extra": "forbid"}


class StockRequest(BaseModel):
    symbol: str

    model_config = {"extra": "forbid"}


class CalculationRequest(BaseModel):
    expression: str

    model_config = {"extra": "forbid"}


class RunResult(BaseModel):
    """Aggregated pipeline result for agent consumption (non-streaming).

    A projection of ``application.services.agent_results.RunSummary``. Field
    names match the TypeScript SDK's ``expected_summary`` in
    ``sdk/contract/events.json`` so both clients read the same run the same way.
    """
    preset: str
    method: str | None = None
    errors: list[str] = []
    total_tokens: dict[str, int] = {"input": 0, "output": 0, "total": 0}
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    synthesis: str = ""
    critical_insights: list[str] = []
    open_questions: list[str] = []
    claim_labels: dict[str, str] = {}
    premises: list[dict] = []
    action_blueprint: list[dict] = []
    citations: list[dict] = []
    models_used: list[str] = []

    model_config = {"extra": "forbid"}


class DiscoverRequest(BaseModel):
    topic: str = "tech"
    mode: str = "normal"

    model_config = {"extra": "forbid"}
