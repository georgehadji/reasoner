"""
Single source of truth for all hardcoded constants used across the Reasoner project.

This module contains ONLY pure constants (no I/O, no environment reads, no side effects)
so it is safe to import from anywhere without risk of circular dependencies or
unexpected initialization order issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from reasoner.core.constants_models import MODEL_GEMINI_FLASH, MODEL_GEMINI_FLASH_LITE  # needed for IMAGE_GEN_ENHANCEMENT_MODEL + QUALITY_JUDGE_MODELS
from typing import Literal

# ═════════════════════════════════════════════════════════════════════
# DEFAULTS
# ═════════════════════════════════════════════════════════════════════

DEFAULT_MAX_TOKENS: int = 2048
DEFAULT_TEMPERATURE: float = 0.7
DEFAULT_TOP_K: int = 2
DEFAULT_PRESET: str = "multi-perspective-budget"
DEFAULT_CLI_PRESET: str = "multi-perspective-budget"
DEFAULT_SEQUENTIAL: bool = False
DEFAULT_SOURCE_TYPE: Literal["general", "academic", "social", "news", "code"] = "general"
DEFAULT_NUM_SUGGESTIONS: int = 5
DEFAULT_SEARCH_RESULTS: int = 10
DEFAULT_MAX_DECOMPOSED_QUERIES: int = 3
DEFAULT_CIRCUIT_BREAKER_THRESHOLD: int = 3
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BACKOFF_BASE: int = 2
DEFAULT_BACKOFF_DELAY: float = 1.0
DEFAULT_HEARTBEAT_INTERVAL: float = 30.0
DEFAULT_SNAPSHOT_INTERVAL: float = 60.0
DEFAULT_DB_COMMAND_TIMEOUT: int = 60
CORS_MAX_AGE_SECONDS: int = 86400
MAX_CACHE_FILES: int = 1000
MAX_CIRCUIT_BREAKER_REGISTRY_SIZE: int = 1000
MAX_RATE_LIMIT_BUCKETS: int = 10000
SNAPSHOT_LIST_LIMIT: int = 1000
DEFAULT_SANITIZER_MAX_LENGTH: int = 10000
DEFAULT_API_PORT: int = 8003
SSE_FLUSH_INTERVAL: float = 0.02
VALIDATION_TEST_MAX_TOKENS: int = 1

# ═════════════════════════════════════════════════════════════════════
# GATE AGENT
# ═════════════════════════════════════════════════════════════════════

GATE_MAX_TOKENS: int = 256
GATE_TEMPERATURE: float = 0.0
GATE_TIMEOUT_SECONDS: float = 5.0
GATE_CONFIDENCE_THRESHOLD: float = 0.70
GATE_DEFAULT_MODEL: str = "gemini-flash"  # non-OpenAI model that supports temperature=0

# ═════════════════════════════════════════════════════════════════════
# HYPERGATE AGENT (sub-agent orchestrator replacing GateAgent)
# ═════════════════════════════════════════════════════════════════════

HYPERGATE_DIRECT_THRESHOLD: float = 0.80   # DirectDetector confidence floor
HYPERGATE_WEB_THRESHOLD: float = 0.65      # WebDetector confidence floor
HYPERGATE_METHOD_THRESHOLD: float = 0.70   # MethodClassifier confidence floor
HYPERGATE_AMBIGUOUS_FLOOR: float = 0.45    # Below this on all agents → hard fallback
HYPERGATE_TIMEOUT_SECONDS: float = 6.0     # Per-sub-agent call timeout
HYPERGATE_CACHE_SIZE: int = 512            # LRU size (per sub-agent + top-level)
HYPERGATE_CACHE_TTL_SECONDS: int = 3600  # 1-hour TTL for top-level routing decisions
HYPERGATE_MAX_TOKENS_LANGUAGE: int = 80
HYPERGATE_MAX_TOKENS_COMPLEXITY: int = 80
HYPERGATE_MAX_TOKENS_DIRECT: int = 100
HYPERGATE_MAX_TOKENS_WEB: int = 100
HYPERGATE_MAX_TOKENS_METHOD: int = 128
HYPERGATE_MAX_TOKENS_TIEBREAK: int = 200

# ═════════════════════════════════════════════════════════════════════
# TOKEN BUDGETS
# ═════════════════════════════════════════════════════════════════════

PHASE_TOKEN_BUDGETS: dict[str, int] = {
    # Phase Fusion: Combined classification and decomposition
    "fusion": 1536,
    # Phase 2: Perspective analysis - moderate detail
    "perspective": 1536,
    "constructive": 1536,
    "destructive": 2560,
    "systemic": 1536,
    "minimalist": 1536,
    # Phase 3: Critique - scores + brief rationale
    "critique": 1024,
    "scoring": 1024,
    # Phase 4: Stress testing - scenario results
    "stress_testing": 1024,
    # Phase 5: Synthesis - comprehensive final output
    # Budget increased to 32K to leverage qwen3.6-plus's 1M context window
    "synthesis": 32768,
    # Method-specific phases
    "debate_opening": 1024,
    "debate_rebuttal": 1024,
    "debate_judge": 1024,
    "jury_generator": 1536,
    "jury_critic": 1024,
    "jury_verifier": 1024,
    "iterative_generate": 1536,
    "iterative_critique": 1024,
    "research": 4096,
    "verification": 1024,
    "deep_read": 2048,
    "deep_read_shallow": 512,
    "cross_verify": 1024,
    # Additional roles
    "prism_classify":         256,
    "recovery_path":         1024,
    "search_disambiguation":  256,
    # Coding pipeline — each generate call produces a full file; 1536 (default)
    # truncates mid-JSON for any real-world module. 8192 fits most files; assemble
    # consolidates multiple files so it needs the largest budget of the group.
    "coding_spec":      4096,
    "coding_generate":  8192,
    "coding_review":    4096,
    "coding_tests":     8192,
    "coding_assemble": 16384,
    # Default fallback
    "default": 1536,
}


def get_token_budget(role: str) -> int:
    """Get token budget for a specific role/phase."""
    return PHASE_TOKEN_BUDGETS.get(role, PHASE_TOKEN_BUDGETS["default"])


# ═════════════════════════════════════════════════════════════════════
# PHASE QUALITY MONITOR — RETRY BUDGETS
# ═════════════════════════════════════════════════════════════════════

PHASE_RETRY_BUDGETS: dict[str, int] = {
    "Synthesis":             2,
    "Final Assembly":        2,
    "Decompose Topic":       2,
    "Extract Claims (CoVE)": 1,
    "Perspectives":          1,
    "Critique & Pruning":    1,
    "Stress Testing":        1,
    "Decomposition":         1,
    "default":               1,
}


def get_phase_retry_budget(phase_name: str) -> int:
    """Return the maximum number of retries allowed for a given phase."""
    return PHASE_RETRY_BUDGETS.get(phase_name, PHASE_RETRY_BUDGETS["default"])


# ═════════════════════════════════════════════════════════════════════
# PHASE QUALITY MONITOR — JUDGE MODELS & THRESHOLDS
# ═════════════════════════════════════════════════════════════════════

QUALITY_JUDGE_MODELS: dict[str, str] = {
    "budget":  MODEL_GEMINI_FLASH_LITE,
    "premium": MODEL_GEMINI_FLASH,
    "default": MODEL_GEMINI_FLASH_LITE,
}

QUALITY_JUDGE_THRESHOLDS: dict[str, float] = {
    "budget":  6.0,
    "premium": 7.0,
    "default": 6.0,
}


def get_quality_judge_model(preset_name: str) -> str:
    """Return the LLM model to use for quality judging based on preset tier."""
    if "premium" in preset_name:
        return QUALITY_JUDGE_MODELS["premium"]
    if "budget" in preset_name:
        return QUALITY_JUDGE_MODELS["budget"]
    return QUALITY_JUDGE_MODELS["default"]


def get_quality_judge_threshold(preset_name: str) -> float:
    """Return the minimum score required to pass quality evaluation."""
    if "premium" in preset_name:
        return QUALITY_JUDGE_THRESHOLDS["premium"]
    return QUALITY_JUDGE_THRESHOLDS["default"]


# ═════════════════════════════════════════════════════════════════════
# BASE URLs
# ═════════════════════════════════════════════════════════════════════

DEFAULT_SEARXNG_URL: str = "http://localhost:8888"
DEFAULT_NEURO_URL: str = "http://localhost:50001"
DEFAULT_OLLAMA_URL: str = "http://localhost:11434"
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL: str = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
GOOGLE_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
PERPLEXITY_BASE_URL: str = "https://api.perplexity.ai"
NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
OPENMETEO_GEOCODING_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
OPENMETEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
DEEPL_FREE_BASE_URL: str = "https://api-free.deepl.com/v2"
DEEPL_PAID_BASE_URL: str = "https://api.deepl.com/v2"
HUGGINGFACE_API_BASE: str = "https://api-inference.huggingface.co"
OPENROUTER_AUTH_KEY_URL: str = "https://openrouter.ai/api/v1/auth/key"
YOUTUBE_OEMBED_URL: str = "https://www.youtube.com/oembed"
YOUTUBE_WATCH_BASE_URL: str = "https://www.youtube.com/watch?v="

# ═════════════════════════════════════════════════════════════════════
# GROUPED LIMITS (Value Object Pattern via frozen dataclasses)
# ═════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Timeouts:
    HEALTH_CHECK: float = 5.0
    EMBEDDING: float = 15.0
    SEARCH_CLIENT: float = 30.0
    SCRAPER: float = 30.0
    WIDGET: float = 10.0
    WIDGET_SHORT: float = 5.0
    MODEL_VALIDATION: float = 10.0
    HTTP_TOTAL: float = 120.0
    HTTP_CONNECT: float = 10.0
    LLM_CALL: float = 120.0    # v3.1: raised from 45s for complex reasoning prompts
    # Phase-specific timeouts — tighter budgets per role
    CLASSIFICATION: float = 20.0
    DECOMPOSITION: float = 60.0
    SYNTHESIS: float = 120.0   # synthesis legitimately needs more time


# Maps routing role names to their specific call timeout.
# Roles absent from this map use TIMEOUTS.LLM_CALL as the default.
ROLE_TIMEOUTS: dict[str, str] = {
    "classification": "CLASSIFICATION",
    "prompt_enhancement": "CLASSIFICATION",
    "decomposition": "DECOMPOSITION",
    "synthesis": "SYNTHESIS",
}


@dataclass(frozen=True)
class TruncationLimits:
    PROBLEM: int = 500
    CONTENT: int = 800
    SNIPPET: int = 500
    API_STORAGE: int = 200
    KEY_INSIGHTS: int = 3
    MEMORY: int = 2
    SESSION_LOG: int = 200
    SESSION_EXCERPT: int = 100
    ASSUMPTION: int = 150
    SOLUTION: int = 4000
    PROMPT: int = 300
    LARGE_CONTENT: int = 16000
    DEEP_READ: int = 8000


TIMEOUTS = Timeouts()
TRUNCATION = TruncationLimits()

# ═════════════════════════════════════════════════════════════════════
# PHASE TIMEOUTS (SSE streaming — per-phase automatic cancellation)
# ═════════════════════════════════════════════════════════════════════

PHASE_TIMEOUTS: dict[str, float] = {
    "Classification": 20.0,
    "Decomposition": 60.0,
    "Deep Read": 45.0,
    "Perspectives": 90.0,
    "Opening Statements": 60.0,
    "Rebuttals": 60.0,
    "Cross-Examination": 60.0,
    "Hypotheses": 60.0,
    "Falsification Tests": 60.0,
    "Maieutic Questions": 60.0,
    "Dialectic Answers": 60.0,
    "Generation Pool": 90.0,
    "VS Idea Generation": 180.0,
    "Critic Pool": 90.0,
    "Verification & Meta": 90.0,
    "Deep Research": 120.0,
    "Critique & Pruning": 90.0,
    "Stress Testing": 90.0,
    "Synthesis": 240.0,
    # Writing flow — composite SoT phase bundles skeleton + parallel writes + assembly
    "Synthesize (SoT)": 180.0,
    # Writing flow — web retrieval can be slow; parallel searches still need room
    "Retrieve Sources": 240.0,
    "Extract Claims (CoVE)": 120.0,
    "Adversarial Verify": 120.0,
    "Pre-Mortem": 90.0,
    "Journal Review": 90.0,
    "Final Assembly": 120.0,
    "Humanize": 90.0,
    # Brainstorming (Verbalized Sampling) — sequential multi-round LLM calls need headroom
    "VS Idea Generation": 300.0,   # 5 rounds × ~45s each worst-case
    "Cluster & Score": 120.0,
    "Deep Development": 180.0,
    "default": 90.0,
}


def get_phase_timeout(phase_name: str) -> float:
    """Get the automatic timeout for a given phase name.

    If the phase is not explicitly configured, returns the default timeout.
    """
    return PHASE_TIMEOUTS.get(phase_name, PHASE_TIMEOUTS["default"])

# ═════════════════════════════════════════════════════════════════════
# PROMPT / JSON CONSTANTS
# ═════════════════════════════════════════════════════════════════════

JSON_ONLY_FOOTER: str = "Output ONLY valid JSON."

# ═════════════════════════════════════════════════════════════════════
# IMAGE GENERATION
# ═════════════════════════════════════════════════════════════════════

IMAGE_GEN_BUDGET_PRESET: str = "image-gen-budget"
IMAGE_GEN_PREMIUM_PRESET: str = "image-gen-premium"
IMAGE_GEN_PRESET_ALIASES: tuple[str, str] = ("budget", "premium")
IMAGE_GEN_ALLOWED_PRESETS: tuple[str, str] = (
    IMAGE_GEN_BUDGET_PRESET,
    IMAGE_GEN_PREMIUM_PRESET,
)
IMAGE_GEN_DEFAULT_PRESET: str = IMAGE_GEN_BUDGET_PRESET
IMAGE_GEN_DEFAULT_ASPECT_RATIO: str = "1:1"
IMAGE_GEN_ALLOWED_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "16:9", "9:16", "4:3", "3:4")
IMAGE_GEN_DEFAULT_RESOLUTION: str = "1024x1024"
IMAGE_GEN_DEFAULT_WIDTH: int = 1024
IMAGE_GEN_DEFAULT_HEIGHT: int = 1024
IMAGE_GEN_REMOTE_TIMEOUT_SECONDS: float = 20.0
IMAGE_GEN_COMPLETION_TIMEOUT_SECONDS: float = 90.0
IMAGE_GEN_ENHANCEMENT_MODEL: str = MODEL_GEMINI_FLASH
IMAGE_GEN_PRESETS: dict[str, list[str]] = {
    "budget": ["grok-imagine", "riverflow-v2-fast-preview", "gemini-flash-image"],
    "premium": ["gpt-5.4-image-2", "recraft-v4.1-pro"],
    IMAGE_GEN_BUDGET_PRESET: ["grok-imagine", "riverflow-v2-fast-preview", "gemini-flash-image"],
    IMAGE_GEN_PREMIUM_PRESET: ["gpt-5.4-image-2", "recraft-v4.1-pro"],
}
IMAGE_GEN_FALLBACKS: dict[str, list[str]] = {
    "budget": ["seedream-4.5", "flux.2-pro", "recraft-v4.1-utility"],
    "premium": ["gpt-5-image", "gemini-3.1-flash-image-preview", "mai-image-2.5", "recraft-v4-pro"],
    IMAGE_GEN_BUDGET_PRESET: ["seedream-4.5", "flux.2-pro", "recraft-v4.1-utility"],
    IMAGE_GEN_PREMIUM_PRESET: ["gpt-5-image", "gemini-3.1-flash-image-preview", "mai-image-2.5", "recraft-v4-pro"],
}
IMAGE_GEN_ENHANCEMENT_SYSTEM_PROMPT: str = ""  # moved to constants_prompts.py
IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT: str = ""  # moved to constants_prompts.py

# ═════════════════════════════════════════════════════════════════════
# ARTICLE / ESSAY GENERATION
# ═════════════════════════════════════════════════════════════════════

ARTICLE_MIN_SOURCE_COUNT: int = 8
ARTICLE_MAX_SOURCE_COUNT: int = 16
ARTICLE_SEARCH_RESULTS_PER_QUERY: int = 6
ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION: int = 16
ARTICLE_MIN_CLAIM_SUPPORT_RATIO: float = 0.5
ARTICLE_CRITIC_MAX_WORDS: int = 4000

# ═════════════════════════════════════════════════════════════════════
# DIRECT ANSWER / STREAMING DEFAULTS
# ═════════════════════════════════════════════════════════════════════

CREATIVE_MAX_TOKENS: int = 4096
DIRECT_ANSWER_MAX_TOKENS: int = 2048
CREATIVE_TEMPERATURE: float = 0.8
DIRECT_ANSWER_TEMPERATURE: float = 0.7
MAX_PROBLEM_DISPLAY_CHARS: int = 120

# ═════════════════════════════════════════════════════════════════════
# CALCULATION WIDGET LIMITS
# ═════════════════════════════════════════════════════════════════════

MAX_EXPRESSION_DEPTH: int = 100
MAX_EXPRESSION_LENGTH: int = 10000

# ── Event Store Compaction ──────────────────────────────────────────
EVENT_RETENTION_DAYS: int = 365
SNAPSHOT_RETENTION_COUNT: int = 3   # reserved — current schema supports only 1 snapshot/aggregate
COMPACTION_BATCH_SIZE: int = 500