"""
Centralized environment-aware settings.

This is the ONLY module in the project that reads from the process environment
and loads the .env file. It uses a guard so that `load_dotenv` is executed at
most once, even if the module is imported multiple times.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _dotenv_loaded = False

    def _ensure_dotenv() -> None:
        global _dotenv_loaded
        if not _dotenv_loaded:
            # Load .env first, then .env.local as fallback (Next.js convention).
            # Also check ui-next/.env.local so the backend can share the frontend key.
            # .env uses override=True so it wins over stale shell env vars.
            # Local files use override=False so they only fill gaps.
            root = Path(__file__).parent.parent.parent.parent
            load_dotenv(root / ".env", override=True)
            load_dotenv(root / ".env.local", override=False)
            load_dotenv(root / "ui-next" / ".env.local", override=False)
            _dotenv_loaded = True

    _ensure_dotenv()
except ImportError:
    pass


class Settings:
    """Application settings derived from environment variables."""

    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "300"))
    RATE_LIMIT_PER_HOUR: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "5000"))
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", "50"))
    MEMORY_LIMIT_MB: int = int(os.getenv("MEMORY_LIMIT_MB", "4096"))
    MEMORY_WARNING_MB: int = int(os.getenv("MEMORY_WARNING_MB", "3072"))
    REQUEST_TIMEOUT_SECONDS: float = float(
        os.getenv("REQUEST_TIMEOUT_SECONDS", "300.0")
    )
    OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")
    FINE_TUNED_API_KEY: str | None = os.getenv("FINE_TUNED_API_KEY")
    PERPLEXITY_API_KEY: str | None = os.getenv("PERPLEXITY_API_KEY")
    NVIDIA_API_KEY: str | None = os.getenv("NVIDIA_API_KEY")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    SEARXNG_URL: str = os.getenv("SEARXNG_URL", "http://localhost:8888")
    SEARXNG_SECRET_KEY: str = os.getenv("SEARXNG_SECRET_KEY", "")
    ADMIN_API_KEY: str | None = os.getenv("ADMIN_API_KEY")
    REASONER_DEEP_READ_LLM: bool = os.getenv("REASONER_DEEP_READ_LLM", "1") != "0"

    # ── Phase Subagent Feature Flags ──
    USE_SUBAGENT_ENHANCEMENT: bool = os.getenv("USE_SUBAGENT_ENHANCEMENT", "false").lower() == "true"
    USE_SUBAGENT_DECOMPOSITION: bool = os.getenv("USE_SUBAGENT_DECOMPOSITION", "false").lower() == "true"
    USE_SUBAGENT_CRITIQUE: bool = os.getenv("USE_SUBAGENT_CRITIQUE", "false").lower() == "true"
    USE_SUBAGENT_SYNTHESIS: bool = os.getenv("USE_SUBAGENT_SYNTHESIS", "false").lower() == "true"
    USE_SUBAGENT_SEARCH: bool = os.getenv("USE_SUBAGENT_SEARCH", "false").lower() == "true"

    # ── Environment / Deployment ──
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    UVICORN_WORKERS: int = int(os.getenv("UVICORN_WORKERS", "1"))
    ENABLE_LEGACY_API_KEY: bool = os.getenv("ENABLE_LEGACY_API_KEY", "false").lower() in ("1", "true", "yes")

    # ── Cohere Rerank (via OpenRouter) ──
    COHERE_RERANK_ENABLED: bool = os.getenv("COHERE_RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
    COHERE_RERANK_MODEL: str = os.getenv("COHERE_RERANK_MODEL", "cohere/rerank-4-fast")

    # ── Document Semantic Retrieval (Phase 4, opt-in) ──
    DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED: bool = os.getenv("DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", "false").lower() in ("1", "true", "yes")
    DOCUMENT_CHUNK_SIZE: int = int(os.getenv("DOCUMENT_CHUNK_SIZE", "1000"))
    DOCUMENT_CHUNK_OVERLAP: int = int(os.getenv("DOCUMENT_CHUNK_OVERLAP", "200"))
    DOCUMENT_MAX_CHUNKS_PER_FILE: int = int(os.getenv("DOCUMENT_MAX_CHUNKS_PER_FILE", "500"))

    # ── Server bind configuration ──
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3000")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8003"))
    UVICORN_HOST: str = os.getenv("UVICORN_HOST", "127.0.0.1")
    METRICS_ALLOWED_IPS: str = os.getenv("METRICS_ALLOWED_IPS", "127.0.0.1,::1")

    # ── CSRF ──
    CSRF_SECRET: str | None = os.getenv("CSRF_SECRET")
    CSRF_ENFORCE_BACKEND: bool = os.getenv("CSRF_ENFORCE_BACKEND", "true").lower() in ("1", "true", "yes")

    # ── Auth / Supabase ──
    AUTH_PERSISTENCE_ENABLED: bool = os.getenv("AUTH_PERSISTENCE_ENABLED", "false").lower() in ("1", "true", "yes")
    AUTH_DB_PATH: str = os.getenv("AUTH_DB_PATH", "src/reasoner/auth_keys.db")
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: str | None = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    JWT_SECRET_KEY: str | None = os.getenv("JWT_SECRET_KEY")

    # ── Rate Limiter / Circuit Breaker Mode ──
    RATE_LIMITER_MODE: str = os.getenv("RATE_LIMITER_MODE", "redis")
    CIRCUIT_BREAKER_MODE: str = os.getenv("CIRCUIT_BREAKER_MODE", "redis")

    # ── CORS ──
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8003,http://127.0.0.1:8003"
    )

    # ── DeepL Translation ──
    DEEPL_API_KEY: str | None = os.getenv("DEEPL_API_KEY")

    # ── OpenRouter analytics headers ──
    OPENROUTER_HTTP_REFERER: str = os.getenv(
        "OPENROUTER_HTTP_REFERER", "https://github.com/Reasoner"
    )
    OPENROUTER_APP_TITLE: str = os.getenv("OPENROUTER_APP_TITLE", "Reasoner")

    # ── Neuro Memory Models ──
    NEURO_REASONING_MODEL: str = os.getenv("NEURO_REASONING_MODEL", "openai/gpt-4o-mini")
    NEURO_REASONING_FALLBACK_MODELS: str = os.getenv(
        "NEURO_REASONING_FALLBACK_MODELS",
        "google/gemini-2.0-flash-001,anthropic/claude-3-haiku",
    )
    NEURO_EMBEDDING_MODEL: str = os.getenv("NEURO_EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")
    NEURO_EMBEDDING_FALLBACK_MODELS: str = os.getenv(
        "NEURO_EMBEDDING_FALLBACK_MODELS",
        "openai/text-embedding-3-small,baai/bge-m3",
    )

    # ── Sentry ──
    SENTRY_DSN: str | None = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    # ── Langfuse (LLM Observability) ──
    LANGFUSE_PUBLIC_KEY: str | None = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: str | None = os.getenv("LANGFUSE_SECRET_KEY")

    # ── Stripe Billing ──
    STRIPE_SECRET_KEY: str | None = os.getenv("STRIPE_SECRET_KEY")

    # ── Scraping ──
    SCRAPE_USER_AGENT: str = os.getenv(
        "SCRAPE_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    # ── Rerank ──
    RERANK_API_BASE: str = os.getenv("RERANK_API_BASE", "https://openrouter.ai/api/v1")

    # ── Database ──
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "50"))

    @property
    def internal_api_base_url(self) -> str:
        """Base URL for internal self-calls (e.g., Neuro endpoints from streaming)."""
        return f"http://{self.SERVER_HOST}:{self.SERVER_PORT}"

    @property
    def neuro_reasoning_fallbacks(self) -> list[str]:
        """Parse NEURO_REASONING_FALLBACK_MODELS into a list."""
        return [m.strip() for m in self.NEURO_REASONING_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def neuro_embedding_fallbacks(self) -> list[str]:
        """Parse NEURO_EMBEDDING_FALLBACK_MODELS into a list."""
        return [m.strip() for m in self.NEURO_EMBEDDING_FALLBACK_MODELS.split(",") if m.strip()]

    # ── Trusted Proxies ──
    TRUSTED_PROXIES: list[str] = [
        p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()
    ]

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS env var into a list of origin strings."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
