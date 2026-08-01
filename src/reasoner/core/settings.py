"""
Centralized environment-aware settings (pydantic-settings).

This is the ONLY module in the project that reads from the process environment
and loads the .env file.  Every other module receives its configuration via
constructor injection from the composition root (*asgi.py* / *main.py*).

Architecture:
    Parse, don't validate — the types of ``Settings`` guarantee the invariants,
    so downstream code never re-checks ``if settings.CSRF_SECRET``.
    ``str`` keeps credentials out of ``repr()``.
    ``frozen=True`` prevents mid-process mutation (which would make testing
    and cache isolation impossible).

Transition (two-step):
    1. Log-only release: if production invariants are violated, warn but continue.
    2. Enforce release: raise ``ValueError`` on violation.
    Set ``SETTINGS_ENFORCE_VALIDATION`` to ``"true"`` to skip step 1.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from reasoner.core.constants_models import (
    MODEL_CLAUDE_HAIKU,
    MODEL_GEMINI_FLASH,
    MODEL_GPT4O_MINI,
)

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────


# ── Environment enum ──────────────────────────────────────────────


class Environment(str):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


# ── Settings class ────────────────────────────────────────────────


class Settings(BaseSettings):
    """Application settings derived from environment variables.

    All values come from the environment / .env file.  Every field has
    a sensible development default.  Production deployments must set
    the required-production variables (listed in ``_REQUIRED_IN_PRODUCTION``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # NOT frozen.  Freezing is the desired end state (see F-13 in
        # plans/PRODUCTION_READINESS_PLAN.md) but pydantic raises
        # ValidationError on assignment to a frozen model, which breaks the
        # 38 `patch.object(settings, ...)` call sites across 7 test modules
        # — including the security regression suite.  Reinstate `frozen=True`
        # only together with a fixture that builds a fresh Settings instance
        # instead of patching the shared one.
    )

    # ── API Keys (LLM Providers) ──
    OPENROUTER_API_KEY: str | None = Field(None, alias="OPENROUTER_API_KEY")
    OPENAI_API_KEY: str | None = Field(None, alias="OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    MISTRAL_API_KEY: str | None = Field(None, alias="MISTRAL_API_KEY")
    DEEPSEEK_API_KEY: str | None = Field(None, alias="DEEPSEEK_API_KEY")
    XAI_API_KEY: str | None = Field(None, alias="XAI_API_KEY")
    FINE_TUNED_API_KEY: str | None = Field(None, alias="FINE_TUNED_API_KEY")
    PERPLEXITY_API_KEY: str | None = Field(None, alias="PERPLEXITY_API_KEY")
    NVIDIA_API_KEY: str | None = Field(None, alias="NVIDIA_API_KEY")
    OLLAMA_BASE_URL: str = Field("http://localhost:11434", alias="OLLAMA_BASE_URL")

    # ── Security / Admin ──
    ADMIN_API_KEY: str | None = Field(None, alias="ADMIN_API_KEY")
    CSRF_SECRET: str | None = Field(None, alias="CSRF_SECRET")
    CSRF_ENFORCE_BACKEND: bool = Field(True, alias="CSRF_ENFORCE_BACKEND")
    JWT_SECRET_KEY: str | None = Field(None, alias="JWT_SECRET_KEY")
    TRUSTED_PROXIES: str = Field("", alias="TRUSTED_PROXIES")

    # ── Environment / Deployment ──
    ENVIRONMENT: str = Field("development", alias="ENVIRONMENT")
    UVICORN_WORKERS: int = Field(1, alias="UVICORN_WORKERS")
    ENABLE_LEGACY_API_KEY: bool = Field(False, alias="ENABLE_LEGACY_API_KEY")

    # ── Rate Limiting ──
    RATE_LIMIT_PER_MINUTE: int = Field(60, alias="RATE_LIMIT_PER_MINUTE")
    RATE_LIMIT_PER_HOUR: int = Field(1000, alias="RATE_LIMIT_PER_HOUR")
    RATE_LIMIT_BURST: int = Field(10, alias="RATE_LIMIT_BURST")
    RATE_LIMITER_MODE: str = Field("redis", alias="RATE_LIMITER_MODE")
    RATE_LIMITER_REDIS_FAILURE_MODE: str = Field("fail_closed", alias="RATE_LIMITER_REDIS_FAILURE_MODE")
    CIRCUIT_BREAKER_MODE: str = Field("redis", alias="CIRCUIT_BREAKER_MODE")
    MEMORY_LIMIT_MB: int = Field(4096, alias="MEMORY_LIMIT_MB")
    MEMORY_WARNING_MB: int = Field(3072, alias="MEMORY_WARNING_MB")
    REQUEST_TIMEOUT_SECONDS: float = Field(300.0, alias="REQUEST_TIMEOUT_SECONDS")

    # ── Server Bind ──
    APP_URL: str = Field("http://localhost:3000", alias="APP_URL")
    SERVER_HOST: str = Field("127.0.0.1", alias="SERVER_HOST")
    SERVER_PORT: int = Field(8003, alias="SERVER_PORT")
    UVICORN_HOST: str = Field("127.0.0.1", alias="UVICORN_HOST")
    METRICS_ALLOWED_IPS: str = Field("127.0.0.1,::1", alias="METRICS_ALLOWED_IPS")

    # ── CORS ──
    CORS_ORIGINS: str = Field(
        "http://localhost:3000,http://localhost:8003,http://127.0.0.1:8003,"
        "http://localhost:8004,http://127.0.0.1:8004",
        alias="CORS_ORIGINS",
    )

    # ── Database ──
    DATABASE_URL: str = Field("", alias="DATABASE_URL")
    EVENT_STORE_BACKEND: str = Field("sqlite", alias="EVENT_STORE_BACKEND")

    @property
    def resolved_event_store_backend(self) -> str:
        """Resolve event store backend, with dynamic production default."""
        if self.EVENT_STORE_BACKEND != "sqlite":
            return self.EVENT_STORE_BACKEND
        if self.DATABASE_URL and self.ENVIRONMENT == "production":
            return "postgres"
        return "sqlite"
    DB_POOL_SIZE: int = Field(50, alias="DB_POOL_SIZE")

    # ── Auth / Supabase ──
    AUTH_PERSISTENCE_ENABLED: bool = Field(False, alias="AUTH_PERSISTENCE_ENABLED")
    AUTH_DB_PATH: str = Field("", alias="AUTH_DB_PATH")

    @property
    def resolved_auth_db_path(self) -> str:
        """Auth DB path, defaulting under ``DATA_DIR`` rather than ``src/``."""
        if self.AUTH_DB_PATH:
            return self.AUTH_DB_PATH
        from reasoner.core.paths import default_data_paths

        return str(default_data_paths().auth_db)
    SUPABASE_URL: str | None = Field(None, alias="SUPABASE_URL")
    SUPABASE_ANON_KEY: str | None = Field(None, alias="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str | None = Field(None, alias="SUPABASE_SERVICE_ROLE_KEY")

    # ── Search Backends ──
    BRAVE_SEARCH_API_KEY: str | None = Field(None, alias="BRAVE_SEARCH_API_KEY")
    BRAVE_SEARCH_ENABLED: bool = Field(True, alias="BRAVE_SEARCH_ENABLED")
    TAVILY_API_KEY: str | None = Field(None, alias="TAVILY_API_KEY")
    TAVILY_SEARCH_ENABLED: bool = Field(True, alias="TAVILY_SEARCH_ENABLED")
    TAVILY_EXTRACT_ENABLED: bool = Field(True, alias="TAVILY_EXTRACT_ENABLED")
    OPENROUTER_WEB_SEARCH_ENABLED: bool = Field(True, alias="OPENROUTER_WEB_SEARCH_ENABLED")
    PERPLEXITY_SEARCH_TIER: str = Field("sonar-pro", alias="PERPLEXITY_SEARCH_TIER")
    SEARXNG_URL: str = Field("http://localhost:8888", alias="SEARXNG_URL")

    # ── Stripe Billing ──
    STRIPE_SECRET_KEY: str | None = Field(None, alias="STRIPE_SECRET_KEY")

    # ── Cohere Rerank ──
    COHERE_RERANK_ENABLED: bool = Field(True, alias="COHERE_RERANK_ENABLED")
    COHERE_RERANK_MODEL: str = Field("cohere/rerank-4-fast", alias="COHERE_RERANK_MODEL")

    # ── Nemotron Rerank ──
    NEMOTRON_RERANK_ENABLED: bool = Field(False, alias="NEMOTRON_RERANK_ENABLED")
    NEMOTRON_RERANK_MODEL: str = Field(
        "nvidia/llama-nemotron-rerank-vl-1b-v2:free", alias="NEMOTRON_RERANK_MODEL"
    )
    NEMOTRON_RERANK_CONCURRENCY: int = Field(5, alias="NEMOTRON_RERANK_CONCURRENCY")

    # ── Rerank ──
    RERANK_API_BASE: str = Field("https://openrouter.ai/api/v1", alias="RERANK_API_BASE")
    SEMANTIC_RERANK_VETTING: bool = Field(False, alias="SEMANTIC_RERANK_VETTING")

    # ── Document Semantic Retrieval ──
    DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED: bool = Field(False, alias="DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED")
    DOCUMENT_CHUNK_SIZE: int = Field(1000, alias="DOCUMENT_CHUNK_SIZE")
    DOCUMENT_CHUNK_OVERLAP: int = Field(200, alias="DOCUMENT_CHUNK_OVERLAP")
    DOCUMENT_MAX_CHUNKS_PER_FILE: int = Field(500, alias="DOCUMENT_MAX_CHUNKS_PER_FILE")

    # ── DeepL Translation ──
    DEEPL_API_KEY: str | None = Field(None, alias="DEEPL_API_KEY")

    # ── Sentry ──
    SENTRY_DSN: str | None = Field(None, alias="SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(0.1, alias="SENTRY_TRACES_SAMPLE_RATE")

    # ── Langfuse ──
    LANGFUSE_PUBLIC_KEY: str | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: str | None = Field(None, alias="LANGFUSE_SECRET_KEY")

    # ── Spend Caps ──
    SPEND_CAP_PER_RUN_USD: float = Field(0.0, alias="SPEND_CAP_PER_RUN_USD")
    SPEND_CAP_MONTHLY_USD: float = Field(0.0, alias="SPEND_CAP_MONTHLY_USD")

    # ── Resend (Email) ──
    RESEND_API_KEY: str | None = Field(None, alias="RESEND_API_KEY")
    RESEND_FROM_ADDRESS: str = Field(
        "Reasoner <notifications@reasoner.app>", alias="RESEND_FROM_ADDRESS"
    )
    NOTIFICATION_EMAIL: str | None = Field(None, alias="NOTIFICATION_EMAIL")

    # ── Scraping ──
    SCRAPE_USER_AGENT: str = Field(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        alias="SCRAPE_USER_AGENT",
    )

    # ── OpenRouter Analytics ──
    OPENROUTER_HTTP_REFERER: str = Field(
        "https://github.com/Reasoner", alias="OPENROUTER_HTTP_REFERER"
    )
    OPENROUTER_APP_TITLE: str = Field("Reasoner", alias="OPENROUTER_APP_TITLE")

    # ── Neuro Memory Models ──
    NEURO_REASONING_MODEL: str = Field(MODEL_GPT4O_MINI, alias="NEURO_REASONING_MODEL")
    NEURO_REASONING_FALLBACK_MODELS: str = Field(
        f"{MODEL_GEMINI_FLASH},{MODEL_CLAUDE_HAIKU}",
        alias="NEURO_REASONING_FALLBACK_MODELS",
    )
    NEURO_EMBEDDING_MODEL: str = Field(
        "qwen/qwen3-embedding-8b", alias="NEURO_EMBEDDING_MODEL"
    )
    NEURO_EMBEDDING_FALLBACK_MODELS: str = Field(
        "openai/text-embedding-3-small,baai/bge-m3",
        alias="NEURO_EMBEDDING_FALLBACK_MODELS",
    )

    # ── ACR (Adaptive Capability Router) ──
    ACR_ENABLED: bool = Field(False, alias="ACR_ENABLED")
    ACR_MODE: str = Field("shadow", alias="ACR_MODE")
    ACR_LEARNING_ENABLED: bool = Field(False, alias="ACR_LEARNING_ENABLED")
    ACR_BENCHMARKS_ENABLED: bool = Field(False, alias="ACR_BENCHMARKS_ENABLED")
    ACR_EXPLORATION_RATE_BUDGET: float = Field(0.15, alias="ACR_EXPLORATION_RATE_BUDGET")
    ACR_EXPLORATION_RATE_PREMIUM: float = Field(0.05, alias="ACR_EXPLORATION_RATE_PREMIUM")
    ACR_TELEMETRY_DB: str = Field(
        str(Path.home() / ".reasoner" / "acr" / "telemetry.db"),
        alias="ACR_TELEMETRY_DB",
    )
    ACR_PROFILES_PATH: str = Field(
        str(Path.home() / ".reasoner" / "acr" / "capability_profiles.json"),
        alias="ACR_PROFILES_PATH",
    )
    ACR_BENCHMARK_WARMUP_CALLS: int = Field(50, alias="ACR_BENCHMARK_WARMUP_CALLS")

    # ── Prism ──
    PRISM_RESEARCHER_ENABLED: bool = Field(False, alias="PRISM_RESEARCHER_ENABLED")
    PRISM_CLASSIFIER_ENABLED: bool = Field(False, alias="PRISM_CLASSIFIER_ENABLED")
    PRISM_FILE_SEARCH_ENABLED: bool = Field(False, alias="PRISM_FILE_SEARCH_ENABLED")
    PRISM_RERANK_ENABLED: bool = Field(False, alias="PRISM_RERANK_ENABLED")
    PRISM_TOOL_CALLING_ENABLED: bool = Field(False, alias="PRISM_TOOL_CALLING_ENABLED")

    # ── Feature Flags ──
    REASONER_DEEP_READ_LLM: bool = Field(True, alias="REASONER_DEEP_READ_LLM")
    USE_SUBAGENT_ENHANCEMENT: bool = Field(False, alias="USE_SUBAGENT_ENHANCEMENT")
    USE_SUBAGENT_DECOMPOSITION: bool = Field(False, alias="USE_SUBAGENT_DECOMPOSITION")
    USE_SUBAGENT_CRITIQUE: bool = Field(False, alias="USE_SUBAGENT_CRITIQUE")
    USE_SUBAGENT_SYNTHESIS: bool = Field(False, alias="USE_SUBAGENT_SYNTHESIS")
    USE_SUBAGENT_SEARCH: bool = Field(False, alias="USE_SUBAGENT_SEARCH")
    MULTI_PROVIDER_FALLBACK_ENABLED: bool = Field(True, alias="MULTI_PROVIDER_FALLBACK_ENABLED")
    CACHE_SHARE_ANONYMOUS: bool = Field(False, alias="CACHE_SHARE_ANONYMOUS")
    EXEC_SANDBOX_ENABLED: bool = Field(True, alias="EXEC_SANDBOX_ENABLED")
    CODING_VERBALIZED_SAMPLING: bool = Field(True, alias="CODING_VERBALIZED_SAMPLING")
    AUGMENTATION_ENABLED: bool = Field(True, alias="AUGMENTATION_ENABLED")
    AUGMENTATION_LLM_CONFIRM: bool = Field(False, alias="AUGMENTATION_LLM_CONFIRM")
    AUGMENTATION_CACHE_ENABLED: bool = Field(True, alias="AUGMENTATION_CACHE_ENABLED")
    AUGMENTATION_CACHE_MAX_ENTRIES: int = Field(128, alias="AUGMENTATION_CACHE_MAX_ENTRIES")
    AUGMENTATION_CACHE_TTL_SECONDS: int = Field(86400, alias="AUGMENTATION_CACHE_TTL_SECONDS")
    AUGMENTATION_AB_TEST: bool = Field(False, alias="AUGMENTATION_AB_TEST")
    LANGUAGE_PIVOT_ENABLED: bool = Field(True, alias="LANGUAGE_PIVOT_ENABLED")
    LANGUAGE_PROBE_ENABLED: bool = Field(False, alias="LANGUAGE_PROBE_ENABLED")
    TOKEN_DYNAMIC_BUDGETS: bool = Field(True, alias="TOKEN_DYNAMIC_BUDGETS")
    TOKEN_CONTEXT_COMPRESSION: bool = Field(True, alias="TOKEN_CONTEXT_COMPRESSION")
    TOKEN_PROMPT_COMPRESSION: bool = Field(True, alias="TOKEN_PROMPT_COMPRESSION")
    TOKEN_NEURO_COMPRESSION: bool = Field(False, alias="TOKEN_NEURO_COMPRESSION")
    TOKEN_CACHING: bool = Field(True, alias="TOKEN_CACHING")
    COMPACTION_ENABLED: bool = Field(True, alias="COMPACTION_ENABLED")
    COMPACTION_RUN_HOUR_UTC: int = Field(3, alias="COMPACTION_RUN_HOUR_UTC")
    EVENT_RETENTION_DAYS: int = Field(365, alias="EVENT_RETENTION_DAYS")

    # ── Environment override for settings validation ──
    SETTINGS_ENFORCE_VALIDATION: bool = Field(False, alias="SETTINGS_ENFORCE_VALIDATION")

    # ── Derived / computed properties ─────────────────────────────

    @property
    def internal_api_base_url(self) -> str:
        return f"http://{self.SERVER_HOST}:{self.SERVER_PORT}"

    @property
    def neuro_reasoning_fallbacks(self) -> list[str]:
        return [m.strip() for m in self.NEURO_REASONING_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def neuro_embedding_fallbacks(self) -> list[str]:
        return [m.strip() for m in self.NEURO_EMBEDDING_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        return [p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip()]

    # ── Production invariants ─────────────────────────────────────

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        _DEV_CORS_DEFAULT = (
            "http://localhost:3000,http://localhost:8003,http://127.0.0.1:8003,"
            "http://localhost:8004,http://127.0.0.1:8004"
        )
        _REQUIRED_IN_PRODUCTION = ["ADMIN_API_KEY", "CSRF_SECRET", "JWT_SECRET_KEY"]

        if self.ENVIRONMENT != Environment.PRODUCTION:
            return self

        missing = [n for n in _REQUIRED_IN_PRODUCTION if not getattr(self, n, None)]
        if missing:
            msg = f"Missing required production settings: {', '.join(missing)}"
            if self.SETTINGS_ENFORCE_VALIDATION:
                raise ValueError(msg)
            logger.warning("PRODUCTION CONFIG WARNING: %s", msg)

        if self.CORS_ORIGINS == _DEV_CORS_DEFAULT:
            msg = "CORS_ORIGINS must be set explicitly in production"
            if self.SETTINGS_ENFORCE_VALIDATION:
                raise ValueError(msg)
            logger.warning("PRODUCTION CONFIG WARNING: %s", msg)

        return self


# ── Module-level singleton ────────────────────────────────────────
# Instantiated here for backward compatibility with existing code.
# The composition root (asgi.py / main.py) may override specific paths.
settings = Settings()
