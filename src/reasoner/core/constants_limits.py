"""
Single source of truth for all hardcoded constants used across the Reasoner project.

This module contains ONLY pure constants (no I/O, no environment reads, no side effects)
so it is safe to import from anywhere without risk of circular dependencies or
unexpected initialization order issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reasoner.core.constants_models import (
    MODEL_FLUX_2_KLEIN_4B,
    MODEL_GEMINI_31_FLASH_IMAGE_PREVIEW,
    MODEL_GEMINI_FLASH_IMAGE,
    MODEL_GEMINI_PRO_IMAGE,
    MODEL_GPT5_IMAGE,
    MODEL_GPT5_IMAGE_MINI,
    MODEL_GROK_43,
    MODEL_GROK_IMAGINE,
    MODEL_GROK_IMAGINE_IMAGE_2,
    MODEL_MAI_IMAGE_25,
    MODEL_MAI_IMAGE_25_PRO,
    MODEL_QWEN35_FLASH,
    MODEL_RECRAFT_V41,
    MODEL_RECRAFT_V41_PRO,
    MODEL_RIVERFLOW_V25_FAST,
    MODEL_SEEDREAM_45,
)

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
GATE_DEFAULT_MODEL: str = MODEL_GROK_43  # non-OpenAI model that supports temperature=0

# ═════════════════════════════════════════════════════════════════════
# HYPERGATE AGENT (sub-agent orchestrator replacing GateAgent)
# ═════════════════════════════════════════════════════════════════════

HYPERGATE_DIRECT_THRESHOLD: float = 0.80   # DirectDetector confidence floor
HYPERGATE_WEB_THRESHOLD: float = 0.65      # WebDetector confidence floor
HYPERGATE_METHOD_THRESHOLD: float = 0.70   # MethodClassifier confidence floor
HYPERGATE_AMBIGUOUS_FLOOR: float = 0.45    # Below this on all agents → hard fallback
# Per PROVIDER ATTEMPT, not per role. complete_with_retry (infrastructure/
# llm/base.py) retries up to max_retries=2 more times on top of this -- three
# attempts total -- with exponential backoff between them, so one role can
# legitimately cost up to 3x this value plus backoff before its fallback is
# even tried. The old name (HYPERGATE_TIMEOUT_SECONDS) and comment
# ("Per-sub-agent call timeout") both implied a role-level ceiling that does
# not exist.
HYPERGATE_ATTEMPT_TIMEOUT_SECONDS: float = 6.0
# Ceiling on the WHOLE gate decision (all sub-agents, TieBreaker if it fires),
# enforced in gate_service.decide_route via asyncio.wait_for. Interim value --
# measured 2026-08-29 at 5.86s mean for the sub-agent role under 5-way
# concurrency on one endpoint (contention, not model speed; see
# docs/plans/gate-and-registry-remediation.md W4), against 1.9s measured for
# the same model probed alone. 12s covers that mean plus one retry-and-backoff
# cycle without approving an effectively-unbounded wait. Revisit downward once
# W4 spreads the sub-agents across roles/vendors and cuts the contention that
# makes 5.86s the mean today.
HYPERGATE_TOTAL_BUDGET_SECONDS: float = 12.0
HYPERGATE_CACHE_SIZE: int = 512            # LRU size (per sub-agent, in BaseSubAgent)
# Shared L2 cache for the whole gate decision, in gate_service.run_gate_cached.
# core/ports/shared_cache_port.py's docstring already named the "HyperGate L2
# decision cache" as a consumer; W5 is where that became true. Before it, this
# TTL was unused and HyperGateAgent's own _get_l2_cache/_set_l2_cache were
# literally `return None` / `pass` while two documents claimed a working cache.
# Set HYPERGATE_CACHE_ENABLED=False to bypass the lookup without a deploy.
HYPERGATE_CACHE_ENABLED: bool = True
HYPERGATE_CACHE_TTL_SECONDS: int = 3600  # 1-hour TTL for top-level routing decisions
HYPERGATE_MAX_TOKENS_LANGUAGE: int = 80
HYPERGATE_MAX_TOKENS_COMPLEXITY: int = 80
HYPERGATE_MAX_TOKENS_DIRECT: int = 100
HYPERGATE_MAX_TOKENS_WEB: int = 100
HYPERGATE_MAX_TOKENS_METHOD: int = 128
HYPERGATE_MAX_TOKENS_TIEBREAK: int = 200
# On-demand only (image generation), NOT part of the Phase-1 parallel gather.
HYPERGATE_MAX_TOKENS_IMAGE_MODEL: int = 128

# ═════════════════════════════════════════════════════════════════════
# LANGUAGE PIVOT
# ═════════════════════════════════════════════════════════════════════

# Maps human-readable language names (from state.language) to ISO 639-1 codes
# used by DeepL.  Unknown languages return None → DeepL adapter is skipped.
LANG_NAME_TO_ISO: dict[str, str] = {
    "Greek": "EL",
    "Russian": "RU",
    "Arabic": "AR",
    "Chinese": "ZH",
    "Japanese": "JA",
    "Korean": "KO",
    "Spanish": "ES",
    "German": "DE",
    "Turkish": "TR",
    "French": "FR",
    "Italian": "IT",
    "Portuguese": "PT",
    "Dutch": "NL",
    "Polish": "PL",
    "Swedish": "SV",
    "Norwegian": "NB",
    "Danish": "DA",
    "Finnish": "FI",
}

# Methods that generate output natively in the user's language; bypass the
# English pivot so that creative/stylistic integrity is preserved.
NATIVE_LANGUAGE_METHODS: frozenset[str] = frozenset({
    "writing",
    "brainstorming",
    "article",
})

# Cosine distance threshold above which two synthesis texts are considered
# materially divergent.  Tune upward to reduce false positives.
LANGUAGE_DIVERGENCE_COSINE: float = 0.15

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
    # Article pipeline — every one of these roles emits the FULL 800-1200 word
    # article, so DEFAULT_MAX_TOKENS (2048) clips them. article_humanize is the
    # tightest: it returns the article inside a JSON string alongside the tell
    # audit, so escaping and the ai_tells array push it past 2048 even in
    # English. "article" is also a NATIVE_LANGUAGE_METHOD, and EL/RU/AR tokenize
    # 2-3x worse, which is what turned this into silent mid-JSON truncation.
    "article_humanize": 8192,
    "writing_assemble": 8192,
    "writing_draft":    8192,
    "article_revise":   8192,
    # Article editorial roles that were missing entirely and silently fell
    # back to DEFAULT_MAX_TOKENS (2048) — three of them hit that cap exactly
    # on 2026-08-28 (outline and structural-review JSON truncated mid-object;
    # verifier timed out reading the full article + claim ledger). See
    # docs/plans/article-flow-truncation-remediation.md W1.
    "article_sot_skeleton": 4096,  # argument map + per-section outline, structure only
    "article_critic":       4096,  # logical gaps + counterarguments, per-item rationale
    "article_verifier":     8192,  # full article + claim ledger, per-claim verdicts
    "writing_factcheck":    4096,  # ran at 1982/2048 live — 3% headroom
    "egress_rewrite":       8192,  # rewrites a full text blob (see W5)
    # Default fallback
    "default": 1536,
}


def get_token_budget(role: str) -> int:
    """Get token budget for a specific role/phase."""
    return PHASE_TOKEN_BUDGETS.get(role, PHASE_TOKEN_BUDGETS["default"])


# A JSON-contract role that comes back with finish_reason="length" was cut off
# mid-object, not mid-sentence — extract_json() cannot recover from that no
# matter how the prompt is worded. LLMExecutor retries such a role once at
# double its configured budget (see W0); this is the ceiling on that retry so
# a misconfigured role cannot compound into an unbounded spend.
TRUNCATION_RETRY_MAX_TOKENS: int = 16384


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
    "budget":  MODEL_QWEN35_FLASH,
    "premium": MODEL_GROK_43,
    "default": MODEL_QWEN35_FLASH,
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


# ── Multi-Backend Search — method-tier chains ──
# Each method + tier maps to a list of backend names (tried in order).
SEARCH_METHOD_CHAINS: dict[str, dict[str, list[str]]] = {
    "multi_perspective": {
        "budget":  ["perplexity", "tavily", "brave"],
        "premium": ["perplexity", "brave_llm", "tavily"],
    },
    "article": {
        "budget":  ["brave", "tavily", "perplexity"],
        "premium": ["brave_llm", "perplexity_deep", "tavily"],
    },
    "research": {
        "budget":  ["perplexity", "brave", "tavily"],
        "premium": ["perplexity_deep", "brave_llm", "tavily"],
    },
    "prism": {
        "budget":  ["tavily", "brave", "perplexity"],
        "premium": ["brave_llm", "tavily", "perplexity"],
    },
    "direct": {
        "budget":  ["openrouter_web", "tavily", "perplexity"],
        "premium": ["openrouter_web", "brave_llm", "perplexity"],
    },
}

# ── Plan Contract / Feedback Router (#5) ──
# Maximum number of validation commands in a plan contract.
MAX_VALIDATION_COMMANDS: int = 10
# Keywords that flag a coding operation as risky (triggers review).
RISKY_OP_KEYWORDS: tuple[str, ...] = (
    "drop table", "delete from", "rm -rf", "sudo",
    "chmod 777", "format", "mkfs", "dd if=",
)

# ── Evidence Bundle Promotion Tiers (#3) ──
# Sources eligible for VERIFIED status (deterministic/grounded only).
EVIDENCE_SENSOR_SOURCES: tuple[str, ...] = ("sensor", "search")
# Sources capped at HYPOTHESIS (self-attested by LLM).
EVIDENCE_MODEL_SOURCES: tuple[str, ...] = ("model",)

def get_quality_judge_threshold(preset_name: str) -> float:
    """Return the minimum score required to pass quality evaluation."""
    if "premium" in preset_name:
        return QUALITY_JUDGE_THRESHOLDS["premium"]
    return QUALITY_JUDGE_THRESHOLDS["default"]


# ═════════════════════════════════════════════════════════════════════
# BASE URLs
# ═════════════════════════════════════════════════════════════════════


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
    SYNTHESIS: float = 240.0   # v3.7: raised from 120→180→240 — article synthesis with full metadata requires 4 min

# Maximum wall-clock time for an entire pipeline run (seconds).
# Set to 0 to disable (unbounded — original behavior).
# Enforced in streaming.py:run_stream() via asyncio.wait_for.
# 600s = 10 minutes covers even research-premium with web search;
# should be generously above the sum of phase timeouts.
PIPELINE_ABSOLUTE_TIMEOUT_SECONDS: float = 600.0


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
    # Characters per recalled Neuro chunk rendered into a prompt. Distinct from
    # MEMORY above, which is a list-slice count. Deliberately tight: a recalled
    # chunk is replayed model output, and keeping each one short both bounds cost
    # and dilutes any single chunk's influence over the run.
    MEMORY_CHUNK: int = 1200
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
    # Article flow — combined humanize + copy edit runs two sequential LLM calls
    # across the full article, and three on the worst path: if the humanize pass
    # returns unparseable JSON it falls back to the prose style edit before the
    # copy edit still runs.
    "Style + Copy Edit": 240.0,
    "Style + Copy Edit (retry)": 240.0,
    # Article flow — phases that were falling through to "default" (90s) and
    # either don't fit in it (Final Audit timed out twice on 2026-08-28 reading
    # a full article + claim ledger) or were never explicit despite siblings
    # above being generously provisioned. See
    # docs/plans/article-flow-truncation-remediation.md W2.
    "Evidence Collection": 180.0,     # parallel web search
    "Argument Map / Outline": 90.0,   # structure only, no prose
    "First Draft": 120.0,             # single call, full article (writing_draft, 8192 budget)
    "Fact Check + Ledger": 120.0,     # web-grounded verification against retrieved sources
    "Structural Review": 120.0,
    "Developmental Edit": 180.0,      # full-article rewrite
    "Final Audit": 180.0,             # full article + ledger, per-claim verdicts
    "Gap Retrieval": 120.0,           # adapter-flow branch
    "Surface Signals": 60.0,          # adapter-flow branch
    "Egress Rewrite": 120.0,
    # Brainstorming (Verbalized Sampling) — sequential multi-round LLM calls need headroom
    "VS Idea Generation": 300.0,   # 5 rounds × ~45s each worst-case
    "Cluster & Score": 120.0,
    # Iterative Critique — adversarial debate runs sustained LLM back-and-forth
    "Adversarial Debate": 180.0,
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
IMAGE_GEN_PROMPT_MAX_TOKENS: int = 512
IMAGE_GEN_PROMPT_TEMPERATURE: float = 0.7
IMAGE_GEN_ENHANCEMENT_MODEL: str = MODEL_GROK_43
# Every tier returns this many images; each preset below carries exactly this
# many primaries so one model failure degrades into a fallback, not a short run.
IMAGE_GEN_IMAGE_COUNT: int = 4
# Hard ceiling on a caller-requested image count. Every image is one paid
# provider call and they are fanned out in parallel, so an unbounded count lets a
# single request fan out across the whole 40+ model image catalogue. Twice the
# designed batch leaves room for a wider spread without turning one request into
# a cost amplifier.
IMAGE_GEN_MAX_IMAGE_COUNT: int = IMAGE_GEN_IMAGE_COUNT * 2
# Both tiers ship exactly IMAGE_GEN_IMAGE_COUNT primaries so a full run needs no
# fallbacks, and each primary is a different lab — one lab outage or one policy
# refusal can never zero out a run.
#
# Ordering is by measured OpenRouter price, re-derived 2026-08-27 from the LIVE
# per-model endpoint (`GET /models/{id}/endpoints`), not from the flat
# `/models` listing: that listing omits image-generation models entirely (11 of
# 50 returned), so anything ranked from it is ranked from a fifth of the
# catalogue. domain/openrouter_models.json is a snapshot and had drifted —
# gemini-2.5-flash-image was half the price it claimed, seedream-5-0-pro a
# fifth of it.
#
# Where a pure generator publishes BOTH a flat `image` price and an
# `image_output` token rate (Qwen, Seed), the tiers are ranked on the HIGHER of
# the two. The two disagree by 3-4x and the flat field is the one that would
# flatter us; ranking on it would put a lab in the budget tier on a number we
# cannot stand behind.
#
# Both tiers ship one model per lab, and both cross a bloc boundary, so no
# single lab outage, house style, or content policy decides a run. Premium is
# ranked on capability with price only breaking ties (the doctrine
# image_model_catalogue.py enforces for automatic selection); budget is ranked
# on price alone.
#
# EVERY alias below returned an image on a live call on 2026-08-27. Price is
# NOT sufficient to earn a slot here, because a cheaper model can be one this
# code path cannot reach at all:
#   * Krea and Qwen are images-API-only — OpenRouter answers chat/completions
#     with "cannot be used with the chat/completions endpoint". They were the
#     two cheapest models in the catalogue and they never produced a pixel.
#     generate_image_with_model() has an images-API branch, but its guard
#     (`"openrouter.ai" not in base_url`) excludes the only base URL it ever
#     runs against, so the branch is dead and these models are unreachable
#     until that is fixed.
#   * gpt-image-2 returns "No endpoints found"; flux.2-pro, flux.2-max,
#     gpt-5.4-image-2 and riverflow-v2.5-pro fail with an empty provider error.
#   * The seedream-5 line 500s; seedream-4.5 is the working ByteDance model and
#     is therefore what carries the cross-bloc slot in both tiers.
# Re-probe before promoting anything back — scripts are throwaway, the rule is
# not: no alias goes in a tier on a price alone.
# Budget: the cheapest working model from each of four labs. Fallbacks are the
# next four cheapest, again one per lab and no lab repeated from the primaries,
# so a lab-wide outage cannot take out a primary and its own understudy.
IMAGE_GEN_BUDGET_MODELS: list[str] = [
    MODEL_FLUX_2_KLEIN_4B,      # 🇩🇪 Black Forest Labs — $0.0044
    MODEL_RIVERFLOW_V25_FAST,   # 🇺🇸 Sourceful — $0.0059
    MODEL_GROK_IMAGINE_IMAGE_2, # 🇺🇸 xAI — $0.0100
    MODEL_GPT5_IMAGE_MINI,      # 🇺🇸 OpenAI — $0.0103
]
IMAGE_GEN_BUDGET_FALLBACK_MODELS: list[str] = [
    MODEL_RECRAFT_V41,          # 🇺🇸 Recraft — $0.0108
    MODEL_SEEDREAM_45,          # 🇨🇳 ByteDance — $0.0124, cross-bloc diversity
    MODEL_GEMINI_FLASH_IMAGE,   # 🇺🇸 Google — $0.0193
    MODEL_MAI_IMAGE_25,         # 🇺🇸 Microsoft — $0.0606
]
# Premium: the best working model from Google, xAI and OpenAI, plus Recraft for
# the design and in-image-text work the other three are weakest at. OpenAI's
# dedicated image models (gpt-image-2, gpt-5.4-image-2) return no endpoints, so
# its slot is held by the chat-native gpt-5-image.
IMAGE_GEN_PREMIUM_MODELS: list[str] = [
    MODEL_GEMINI_PRO_IMAGE, # 🇺🇸 Google — $0.1548, the pro line beats the flash line
    MODEL_GROK_IMAGINE,     # 🇺🇸 xAI — $0.0100, the quality tier
    MODEL_GPT5_IMAGE,       # 🇺🇸 OpenAI — $0.0516
    MODEL_RECRAFT_V41_PRO,  # 🇺🇸 Recraft — $0.0649, design-grade
]
IMAGE_GEN_PREMIUM_FALLBACK_MODELS: list[str] = [
    MODEL_GPT5_IMAGE_MINI,  # 🇺🇸 OpenAI — $0.0103
    MODEL_GEMINI_31_FLASH_IMAGE_PREVIEW,  # 🇺🇸 Google — $0.0774
    MODEL_MAI_IMAGE_25_PRO, # 🇺🇸 Microsoft — $0.1393
    MODEL_SEEDREAM_45,      # 🇨🇳 ByteDance — $0.0124, cross-bloc diversity
]
IMAGE_GEN_PRESETS: dict[str, list[str]] = {
    "budget": IMAGE_GEN_BUDGET_MODELS,
    "premium": IMAGE_GEN_PREMIUM_MODELS,
    IMAGE_GEN_BUDGET_PRESET: IMAGE_GEN_BUDGET_MODELS,
    IMAGE_GEN_PREMIUM_PRESET: IMAGE_GEN_PREMIUM_MODELS,
}
IMAGE_GEN_FALLBACKS: dict[str, list[str]] = {
    "budget": IMAGE_GEN_BUDGET_FALLBACK_MODELS,
    "premium": IMAGE_GEN_PREMIUM_FALLBACK_MODELS,
    IMAGE_GEN_BUDGET_PRESET: IMAGE_GEN_BUDGET_FALLBACK_MODELS,
    IMAGE_GEN_PREMIUM_PRESET: IMAGE_GEN_PREMIUM_FALLBACK_MODELS,
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
