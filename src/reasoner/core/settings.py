"""
Centralized environment-aware settings.

This is the ONLY module in the project that reads from the process environment
and loads the .env file. It uses a guard so that `load_dotenv` is executed at
most once, even if the module is imported multiple times.
"""

from __future__ import annotations

import os
from pathlib import Path

from reasoner.core.constants_models import (
    MODEL_CLAUDE_HAIKU,
    MODEL_GPT4O_MINI,
    MODEL_GROK_43,
)

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

    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_PER_HOUR: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", "10"))
    MEMORY_LIMIT_MB: int = int(os.getenv("MEMORY_LIMIT_MB", "4096"))
    MEMORY_WARNING_MB: int = int(os.getenv("MEMORY_WARNING_MB", "3072"))
    REQUEST_TIMEOUT_SECONDS: float = float(
        os.getenv("REQUEST_TIMEOUT_SECONDS", "300.0")
    )
    OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY")
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
    MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")
    DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")
    XAI_API_KEY: str | None = os.getenv("XAI_API_KEY")
    FINE_TUNED_API_KEY: str | None = os.getenv("FINE_TUNED_API_KEY")
    PERPLEXITY_API_KEY: str | None = os.getenv("PERPLEXITY_API_KEY")
    NVIDIA_API_KEY: str | None = os.getenv("NVIDIA_API_KEY")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
    # Mounts the MCP Streamable-HTTP transport at /mcp. Off by default: most
    # installs use stdio (mcp_server.py) instead. Requires the mcp extra.
    ENABLE_MCP_HTTP: bool = os.getenv("ENABLE_MCP_HTTP", "false").lower() in ("1", "true", "yes")

    # ── Cohere Rerank (via OpenRouter) ──
    COHERE_RERANK_ENABLED: bool = os.getenv("COHERE_RERANK_ENABLED", "true").lower() in ("1", "true", "yes")
    COHERE_RERANK_MODEL: str = os.getenv("COHERE_RERANK_MODEL", "cohere/rerank-4-fast")

    # ── Prism Integration ──
    PRISM_RESEARCHER_ENABLED: bool = os.getenv("PRISM_RESEARCHER_ENABLED", "false").lower() in ("1", "true", "yes")
    PRISM_CLASSIFIER_ENABLED: bool = os.getenv("PRISM_CLASSIFIER_ENABLED", "false").lower() in ("1", "true", "yes")
    PRISM_FILE_SEARCH_ENABLED: bool = os.getenv("PRISM_FILE_SEARCH_ENABLED", "false").lower() in ("1", "true", "yes")
    PRISM_RERANK_ENABLED: bool = os.getenv("PRISM_RERANK_ENABLED", "false").lower() in ("1", "true", "yes")
    PRISM_TOOL_CALLING_ENABLED: bool = os.getenv("PRISM_TOOL_CALLING_ENABLED", "false").lower() in ("1", "true", "yes")

    # ── Document Semantic Retrieval (Phase 4, opt-in) ──
    DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED: bool = os.getenv("DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", "false").lower() in ("1", "true", "yes")

    # Off by default, and it must stay off until someone has diffed a full
    # preset run with it on against one with it off. Turning it on switches
    # the CLI and headless paths from PipelineWorkflowServices.run_phase's bare
    # `await step.fn(...)` fallback onto the real WorkflowRunner: retries,
    # per-phase timeouts, the quality gate and PHASE_* events, none of which
    # have ever executed on this path. Code that has never run is not known to
    # work, so this is a behaviour change behind a switch, not a bug fix.
    # See docs/plans/backend-defect-remediation.md B1 for the staging.
    WORKFLOW_RUNNER_ENABLED: bool = (
        os.getenv("WORKFLOW_RUNNER_ENABLED", "false").lower() in ("1", "true", "yes")
    )
    DOCUMENT_CHUNK_SIZE: int = int(os.getenv("DOCUMENT_CHUNK_SIZE", "1000"))
    DOCUMENT_CHUNK_OVERLAP: int = int(os.getenv("DOCUMENT_CHUNK_OVERLAP", "200"))
    DOCUMENT_MAX_CHUNKS_PER_FILE: int = int(os.getenv("DOCUMENT_MAX_CHUNKS_PER_FILE", "500"))
    # Multipart upload bounds are enforced before parsing where possible and
    # again while streaming each part.  This prevents request-body and file
    # count exhaustion from reaching the document parsers.
    UPLOAD_MAX_FILES: int = int(os.getenv("UPLOAD_MAX_FILES", "10"))
    DOCUMENT_EXTRACTION_TIMEOUT_SECONDS: int = int(
        os.getenv("DOCUMENT_EXTRACTION_TIMEOUT_SECONDS", "60")
    )
    # Reject uploads outright when python-magic isn't installed, rather than
    # silently skipping content-vs-extension validation. An operator who
    # genuinely can't install it sets this False explicitly, on the record.
    UPLOAD_REQUIRE_MIME_VALIDATION: bool = os.getenv(
        "UPLOAD_REQUIRE_MIME_VALIDATION", "true"
    ).lower() in ("1", "true", "yes")
    # Bounded background document-indexing queue (infrastructure/documents/
    # index_queue.py) -- replaces unbounded fire-and-forget indexing tasks.
    DOCUMENT_INDEX_QUEUE_MAXSIZE: int = int(os.getenv("DOCUMENT_INDEX_QUEUE_MAXSIZE", "200"))
    DOCUMENT_INDEX_WORKER_COUNT: int = int(os.getenv("DOCUMENT_INDEX_WORKER_COUNT", "2"))

    # ── Server bind configuration ──
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3000")
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8003"))
    UVICORN_HOST: str = os.getenv("UVICORN_HOST", "127.0.0.1")
    METRICS_ALLOWED_IPS: str = os.getenv("METRICS_ALLOWED_IPS", "127.0.0.1,::1")

    # ── CSRF ──
    CSRF_SECRET: str | None = os.getenv("CSRF_SECRET")
    CSRF_ENFORCE_BACKEND: bool = os.getenv("CSRF_ENFORCE_BACKEND", "true").lower() in ("1", "true", "yes")


    # ── Database & Persistence ──
    # Default to sqlite for dev, postgres for production if URL provided
    EVENT_STORE_BACKEND: str = os.getenv(
        "EVENT_STORE_BACKEND",
        "postgres" if os.getenv("DATABASE_URL") and os.getenv("ENVIRONMENT") == "production" else "sqlite"
    )

    # ── Auth / Supabase ──
    AUTH_PERSISTENCE_ENABLED: bool = os.getenv("AUTH_PERSISTENCE_ENABLED", "false").lower() in ("1", "true", "yes")
    AUTH_DB_PATH: str = os.getenv("AUTH_DB_PATH", "src/reasoner/auth_keys.db")
    SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY: str | None = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    JWT_SECRET_KEY: str | None = os.getenv("JWT_SECRET_KEY")

    # ── Rate Limiter / Circuit Breaker Mode ──
    RATE_LIMITER_MODE: str = os.getenv("RATE_LIMITER_MODE", "redis")
    # "fail_closed": deny requests when Redis is down (safe default; prevents 4× bypass on multi-worker)
    # "fail_open": fall back to per-worker in-memory limiting (allows bypass, but keeps service running)
    RATE_LIMITER_REDIS_FAILURE_MODE: str = os.getenv("RATE_LIMITER_REDIS_FAILURE_MODE", "fail_closed")
    CIRCUIT_BREAKER_MODE: str = os.getenv("CIRCUIT_BREAKER_MODE", "redis")

    # ── Valkey connection (canonical; falls back to REDIS_URL for backward compat) ──
    VALKEY_URL: str = os.getenv(
        "VALKEY_URL",
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    )
    VALKEY_MAX_CONNECTIONS: int = int(
        os.getenv(
            "VALKEY_MAX_CONNECTIONS",
            os.getenv("REDIS_MAX_CONNECTIONS", "100"),
        )
    )

    # ── CORS ──
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8003,http://127.0.0.1:8003,http://localhost:8004,http://127.0.0.1:8004"
    )

    # ── DeepL Translation ──
    DEEPL_API_KEY: str | None = os.getenv("DEEPL_API_KEY")

    # ── OpenRouter analytics headers ──
    OPENROUTER_HTTP_REFERER: str = os.getenv(
        "OPENROUTER_HTTP_REFERER", "https://github.com/Reasoner"
    )
    OPENROUTER_APP_TITLE: str = os.getenv("OPENROUTER_APP_TITLE", "Reasoner")

    # ── Neuro Memory Models ──
    NEURO_REASONING_MODEL: str = os.getenv("NEURO_REASONING_MODEL", MODEL_GPT4O_MINI)
    NEURO_REASONING_FALLBACK_MODELS: str = os.getenv(
        "NEURO_REASONING_FALLBACK_MODELS",
        f"{MODEL_GROK_43},{MODEL_CLAUDE_HAIKU}",
    )
    NEURO_EMBEDDING_MODEL: str = os.getenv("NEURO_EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")
    NEURO_EMBEDDING_FALLBACK_MODELS: str = os.getenv(
        "NEURO_EMBEDDING_FALLBACK_MODELS",
        "openai/text-embedding-3-small,baai/bge-m3",
    )
    # Neuro recall timeout during pipeline preflight (default 10s)
    NEURO_RECALL_TIMEOUT_SECONDS: float = float(
        os.getenv("NEURO_RECALL_TIMEOUT_SECONDS", "10.0")
    )
    # Feed recalled long-term memory into phase prompts. Recall itself always runs
    # (the chunks are surfaced to the client either way); this gates whether they
    # reach a model. Off ⇒ recall is display-only, which is how the system behaved
    # before the loop was closed. See docs/MIND_VIRUS_MITIGATION.md §2.1 — recalled
    # memory is model-authored text re-entering a *different* model's prompt, so it
    # is injected at user-message position only, wrapped, and sanitised on read.
    NEURO_CONTEXT_IN_PROMPTS: bool = os.getenv(
        "NEURO_CONTEXT_IN_PROMPTS", "true"
    ).lower() == "true"
    # Max recalled chunks rendered into a prompt. Dilution across independent inputs
    # is itself a propagation defence — keep this small.
    NEURO_CONTEXT_MAX_CHUNKS: int = int(os.getenv("NEURO_CONTEXT_MAX_CHUNKS", "5"))

    # ── Prompt Hardening (propagation resistance) ──
    # Prepends CONTENT_TRUST_RULE + PROPAGATION_RESISTANCE_RULE to every phase and
    # subagent system prompt. Kill switch for the rare case where the "flag, don't
    # obey" framing degrades output on meta-reasoning topics.
    PROMPT_HARDENING_ENABLED: bool = os.getenv(
        "PROMPT_HARDENING_ENABLED", "true"
    ).lower() == "true"
    # Resistance floor for terminal roles (synthesis, verification). Most of the
    # whitelist is UNMEASURED, so this ships observable-but-not-blocking: the
    # violation is reported at "soft" severity until the routing consequences on
    # the Budget tier are known. Set PROPAGATION_RESISTANCE_ENFORCE=true to make
    # it a hard constraint. 0.0 disables the check entirely.
    PROPAGATION_RESISTANCE_FLOOR: float = float(
        os.getenv("PROPAGATION_RESISTANCE_FLOOR", "0.60")
    )
    PROPAGATION_RESISTANCE_ENFORCE: bool = os.getenv(
        "PROPAGATION_RESISTANCE_ENFORCE", "false"
    ).lower() == "true"

    # ── Multi-Provider Fallback ──
    MULTI_PROVIDER_FALLBACK_ENABLED: bool = os.getenv(
        "MULTI_PROVIDER_FALLBACK_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── LLM JSON Mode ──
    # Sends a json_object response_format on JSON-contract calls to models
    # whose capability profile supports it (infrastructure.llm.utils.
    # _json_response_format), instead of relying on the prose instruction
    # alone. Kill switch for the first release of this behaviour — flip off if
    # it produces unexpected 400s on a model class the capability data got
    # wrong, without a redeploy.
    LLM_JSON_MODE_ENABLED: bool = os.getenv(
        "LLM_JSON_MODE_ENABLED", "true"
    ).lower() in ("1", "true", "yes")

    # ── Cache Isolation ──
    CACHE_SHARE_ANONYMOUS: bool = os.getenv(
        "CACHE_SHARE_ANONYMOUS", "false"
    ).lower() in ("1", "true", "yes")

    # ── Sentry ──
    SENTRY_DSN: str | None = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    # ── Langfuse (LLM Observability) ──
    LANGFUSE_PUBLIC_KEY: str | None = os.getenv("LANGFUSE_PUBLIC_KEY")
    LANGFUSE_SECRET_KEY: str | None = os.getenv("LANGFUSE_SECRET_KEY")

    # ── Spend Caps (P1.9) ──
    SPEND_CAP_PER_RUN_USD: float = float(
        os.getenv("SPEND_CAP_PER_RUN_USD", "0.0")
    )
    """Maximum USD per pipeline run. 0.0 = unlimited."""

    SPEND_CAP_MONTHLY_USD: float = float(
        os.getenv("SPEND_CAP_MONTHLY_USD", "0.0")
    )
    """Maximum USD per user per month. 0.0 = unlimited."""

    # ── Stripe Billing ──
    STRIPE_SECRET_KEY: str | None = os.getenv("STRIPE_SECRET_KEY")

    # ── Transactional Email (P2.14) ──
    RESEND_API_KEY: str | None = os.getenv("RESEND_API_KEY")
    """Resend API key for sending transactional emails. If unset, emails are logged."""

    RESEND_FROM_ADDRESS: str = os.getenv(
        "RESEND_FROM_ADDRESS", "Reasoner <notifications@reasoner.app>"
    )
    """Sender address for transactional emails."""

    NOTIFICATION_EMAIL: str | None = os.getenv("NOTIFICATION_EMAIL")
    """Email address to receive admin notifications (webhook failures, spend cap, etc.)."""

    # ── Scraping ──
    SCRAPE_USER_AGENT: str = os.getenv(
        "SCRAPE_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    # ── Rerank ──
    RERANK_API_BASE: str = os.getenv("RERANK_API_BASE", "https://openrouter.ai/api/v1")
    # Multi-backend search
    BRAVE_SEARCH_API_KEY: str = os.getenv("BRAVE_SEARCH_API_KEY", "")
    BRAVE_SEARCH_ENABLED: bool = os.getenv("BRAVE_SEARCH_ENABLED", "true").lower() == "true"
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    TAVILY_SEARCH_ENABLED: bool = os.getenv("TAVILY_SEARCH_ENABLED", "true").lower() == "true"
    TAVILY_EXTRACT_ENABLED: bool = os.getenv("TAVILY_EXTRACT_ENABLED", "true").lower() == "true"
    # Despite the name, this does NOT enable OpenRouter's `openrouter:web_search`
    # server tool — nothing in this codebase sends that tool. It selects which of
    # two lanes serves a HyperGate `web_search` decision (api/execution/pipeline.py):
    #   true  -> a single grounded answer from PERPLEXITY_SEARCH_TIER below,
    #            authored by the model (api/execution/direct.py)
    #   false -> a rendered list of raw search-backend results
    #            (SearchService.stream_web_search_results)
    # The name is kept rather than corrected because it is a published env var.
    #
    # The server tool was measured against this lane on 2026-09-03 and rejected:
    # 2-6x the cost for an order of magnitude fewer citations (sonar $0.0051 /
    # 13 sources vs gpt-5-nano+exa $0.0107 / 0), and its results enter the model
    # context server-side, bypassing the `<<<EXTERNAL_CONTENT>>>` wrapping in
    # phases/_shared.py:build_web_sources_block that CLAUDE.md lists as a
    # load-bearing propagation-resistance invariant.
    OPENROUTER_WEB_SEARCH_ENABLED: bool = os.getenv("OPENROUTER_WEB_SEARCH_ENABLED", "true").lower() == "true"
    PERPLEXITY_SEARCH_TIER: str = os.getenv("PERPLEXITY_SEARCH_TIER", "sonar-pro")
    # Nemotron Rerank VL: free NVIDIA reranker via OpenRouter chat completions + logprobs.
    # Used as fallback when Cohere rerank fails, or as primary when NEMOTRON_RERANK_ENABLED=true.
    NEMOTRON_RERANK_ENABLED: bool = os.getenv("NEMOTRON_RERANK_ENABLED", "false").lower() in ("1", "true", "yes")
    NEMOTRON_RERANK_MODEL: str = os.getenv("NEMOTRON_RERANK_MODEL", "nvidia/llama-nemotron-rerank-vl-1b-v2:free")
    NEMOTRON_RERANK_CONCURRENCY: int = int(os.getenv("NEMOTRON_RERANK_CONCURRENCY", "5"))
    # When true, applies semantic cross-encoder reranking after BM25+freshness sort and before LLM vetting.
    # Adds ~1-2s latency but meaningfully improves context quality for research/article methods.
    SEMANTIC_RERANK_VETTING: bool = os.getenv("SEMANTIC_RERANK_VETTING", "false").lower() in ("1", "true", "yes")

    # ── Database ──
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # ── Event Store Compaction ──
    COMPACTION_ENABLED: bool = os.getenv("COMPACTION_ENABLED", "true").lower() in ("1", "true", "yes")
    COMPACTION_RUN_HOUR_UTC: int = int(os.getenv("COMPACTION_RUN_HOUR_UTC", "3"))
    EVENT_RETENTION_DAYS: int = int(os.getenv("EVENT_RETENTION_DAYS", "365"))
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "50"))

    @property
    def internal_api_base_url(self) -> str:
        """Base URL for internal self-calls (e.g., Neuro endpoints from streaming)."""
        return f"http://{self.SERVER_HOST}:{self.SERVER_PORT}"

    @property
    def neuro_internal_key(self) -> str:
        """Shared secret gating /api/neuro/*.

        Those endpoints are self-called over loopback by the pipeline, but
        they are mounted on the public app. Ungated, anyone can drive the
        embedding and reasoning providers (unmetered LLM spend via /audit)
        and read or poison another tenant's memory.

        Three processes must agree on this value -- every gunicorn worker
        (self-calls are load balanced across them) and the Next server, whose
        /api/neuro/* proxy routes forward it upstream. So it is one explicit
        env var rather than something derived: a value derived from another
        secret would have to be re-derived identically in TypeScript, and
        would drift the moment either side changed.

        Empty is allowed for local development; api/__init__.py refuses to
        start in production without it.
        """
        return os.getenv("NEURO_INTERNAL_KEY", "").strip()

    @property
    def neuro_reasoning_fallbacks(self) -> list[str]:
        """Parse NEURO_REASONING_FALLBACK_MODELS into a list."""
        return [m.strip() for m in self.NEURO_REASONING_FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def neuro_embedding_fallbacks(self) -> list[str]:
        """Parse NEURO_EMBEDDING_FALLBACK_MODELS into a list."""
        return [m.strip() for m in self.NEURO_EMBEDDING_FALLBACK_MODELS.split(",") if m.strip()]

    # ── Token Optimization Flags ──
    TOKEN_DYNAMIC_BUDGETS: bool = os.getenv("TOKEN_DYNAMIC_BUDGETS", "true").lower() == "true"
    TOKEN_CONTEXT_COMPRESSION: bool = os.getenv("TOKEN_CONTEXT_COMPRESSION", "true").lower() == "true"
    TOKEN_PROMPT_COMPRESSION: bool = os.getenv("TOKEN_PROMPT_COMPRESSION", "true").lower() == "true"
    TOKEN_NEURO_COMPRESSION: bool = os.getenv("TOKEN_NEURO_COMPRESSION", "false").lower() == "true"
    TOKEN_CACHING: bool = os.getenv("TOKEN_CACHING", "true").lower() == "true"
    # Provider-side prompt caching (cache_control breakpoints on the system
    # prompt for Anthropic/Gemini/Qwen). Distinct from TOKEN_CACHING, which is
    # the in-process response cache.
    PROMPT_CACHE_ENABLED: bool = os.getenv("PROMPT_CACHE_ENABLED", "true").lower() == "true"
    # "5m" or "1h". Default 1h: reuse comes from follow-up turns, which usually
    # arrive more than five minutes apart, so a 5m entry would expire unread.
    # Costs 2x to write instead of 1.25x, so it needs a 3rd read to break even.
    # Anthropic only — other providers get a bare ephemeral marker.
    PROMPT_CACHE_TTL: str = os.getenv("PROMPT_CACHE_TTL", "1h")

    # ── Code Execution Sandbox (#1) ──
    # Host-side execution is disabled by default.
    EXEC_SANDBOX_ENABLED: bool = os.getenv("EXEC_SANDBOX_ENABLED", "false").lower() in ("1", "true", "yes")
    # "container": ContainerExecutionSandbox — the approved isolated boundary
    #   (per-job Docker container run by the separate sandbox-worker service).
    # "subprocess": legacy SubprocessExecutor — runs on the API host with only
    #   an AST allowlist, not a security boundary. Dev/local use only; the
    #   production guard below refuses to start with this mode enabled.
    EXEC_SANDBOX_MODE: str = os.getenv("EXEC_SANDBOX_MODE", "container")
    # Internal-network URL of the sandbox-worker service (never exposed to
    # the public internet — see docker-compose.yml's `sandbox-worker`).
    SANDBOX_WORKER_URL: str = os.getenv("SANDBOX_WORKER_URL", "http://sandbox-worker:8901")
    SANDBOX_WORKER_TOKEN: str = os.getenv("SANDBOX_WORKER_TOKEN", "")

    # ── Anonymous Trial Spend Cap (Phase 2 metering) ──
    # Anonymous runs (ENABLE_LEGACY_API_KEY=true, no account) skip the
    # per-user credit ledger entirely -- there's no account to charge. This
    # caps estimated daily spend per client IP so anonymous traffic stays
    # bounded regardless. 50 credits = $0.05/day, enough for a couple of
    # budget-tier trial runs.
    ANONYMOUS_DAILY_CREDIT_CAP: int = int(os.getenv("ANONYMOUS_DAILY_CREDIT_CAP", "50"))

    # ── WebSocket Security (Phase 3 metering) ──
    # Ticket validity window. Short by design: the ticket travels via the
    # Sec-WebSocket-Protocol header for exactly one connection attempt, not
    # as a standing credential -- see application/services/ws_ticket.py.
    WS_TICKET_TTL_SECONDS: int = int(os.getenv("WS_TICKET_TTL_SECONDS", "30"))
    WS_CONNECT_RATE_LIMIT_PER_MINUTE: int = int(
        os.getenv("WS_CONNECT_RATE_LIMIT_PER_MINUTE", "20")
    )

    # ── ACR (Adaptive Capability Router) ──
    ACR_ENABLED: bool = os.getenv("ACR_ENABLED", "false").lower() in ("1", "true", "yes")
    """Master switch for adaptive routing (Phase 5)."""

    ACR_MODE: str = os.getenv("ACR_MODE", "shadow")
    """ACR operating mode: ``shadow``, ``advisory``, or ``adaptive``."""

    ACR_LEARNING_ENABLED: bool = os.getenv("ACR_LEARNING_ENABLED", "false").lower() in ("1", "true", "yes")
    """Online learning separate from telemetry (Phase 6)."""

    ACR_BENCHMARKS_ENABLED: bool = os.getenv("ACR_BENCHMARKS_ENABLED", "false").lower() in ("1", "true", "yes")
    """Benchmark engine separate from learning (Phase 7)."""

    ACR_EXPLORATION_RATE_BUDGET: float = float(
        os.getenv("ACR_EXPLORATION_RATE_BUDGET", "0.15")
    )
    """Explore rate for budget presets (15% by default)."""

    ACR_EXPLORATION_RATE_PREMIUM: float = float(
        os.getenv("ACR_EXPLORATION_RATE_PREMIUM", "0.05")
    )
    """Explore rate for premium presets (5% by default)."""

    ACR_TELEMETRY_DB: str = os.getenv(
        "ACR_TELEMETRY_DB",
        str(Path.home() / ".reasoner" / "acr" / "telemetry.db"),
    )
    """Path to the ACR telemetry SQLite database."""

    ACR_PROFILES_PATH: str = os.getenv(
        "ACR_PROFILES_PATH",
        str(Path.home() / ".reasoner" / "acr" / "capability_profiles.json"),
    )
    """Path to the ACR capability profiles JSON file."""

    ACR_BENCHMARK_WARMUP_CALLS: int = int(
        os.getenv("ACR_BENCHMARK_WARMUP_CALLS", "50")
    )
    """Minimum calls before a model enters the adaptive pool."""

    # ── Verbalized Sampling (Coding) ──
    CODING_VERBALIZED_SAMPLING: bool = os.getenv("CODING_VERBALIZED_SAMPLING", "true").lower() == "true"

    # ── Augmentation (Article/Writing pre-processing) ──
    AUGMENTATION_ENABLED: bool = os.getenv("AUGMENTATION_ENABLED", "true").lower() in ("1", "true", "yes")
    AUGMENTATION_LLM_CONFIRM: bool = os.getenv("AUGMENTATION_LLM_CONFIRM", "false").lower() in ("1", "true", "yes")
    AUGMENTATION_CACHE_ENABLED: bool = os.getenv("AUGMENTATION_CACHE_ENABLED", "true").lower() in ("1", "true", "yes")
    AUGMENTATION_CACHE_MAX_ENTRIES: int = int(os.getenv("AUGMENTATION_CACHE_MAX_ENTRIES", "128"))
    AUGMENTATION_CACHE_TTL_SECONDS: int = int(os.getenv("AUGMENTATION_CACHE_TTL_SECONDS", "86400"))

    # ── Language Pivot & Probe ──
    LANGUAGE_PIVOT_ENABLED: bool = os.getenv("LANGUAGE_PIVOT_ENABLED", "true").lower() in ("1", "true", "yes")
    # Cross-lingual probe: off by default; enable for premium canary presets.
    LANGUAGE_PROBE_ENABLED: bool = os.getenv("LANGUAGE_PROBE_ENABLED", "false").lower() in ("1", "true", "yes")

    # ── Trusted Proxies ──
    TRUSTED_PROXIES: list[str] = [
        p.strip() for p in os.getenv("TRUSTED_PROXIES", "").split(",") if p.strip()
    ]

    # ── Watermark / AI-provenance-mark scrubbing ──
    # See docs/plans/watermark-removal-integration.md Part IX and §10.3.
    # Layer A egress hygiene is on by default (it is a bug fix + injection
    # defense, not a watermark-removal feature).
    #
    # As of 2026-08-19 every scrubbing control defaults ON, an explicit
    # operator decision overriding the plan's §10.3 recommendation to ship
    # the two removal-flavoured ones behind flags:
    #
    #   WATERMARK_LAYER_B_ENABLED       -- one extra cross-bloc LLM call per
    #     run to rewrite the synthesis prose; the pre-run estimate accounts
    #     for it. Best-effort: cannot certify removal against a detector.
    #   WATERMARK_IMAGE_STRIP_GENERATED -- strips the provenance a provider
    #     (Gemini/OpenAI) attached to an image Reasoner itself requested,
    #     before delivery. §10.3 calls this the sharpest case, since it makes
    #     Reasoner the party removing the mark on content it generated.
    #     Distinct from STRIP_UPLOADS, which cleans the user's own file.
    #
    # Deployments in jurisdictions with provider marking duties (EU AI Act
    # Art. 50, California SB 942) should review these two before shipping.
    WATERMARK_EGRESS_LAYER_A: bool = os.getenv("WATERMARK_EGRESS_LAYER_A", "true").lower() in ("1", "true", "yes")
    WATERMARK_INGRESS_INSPECT: bool = os.getenv("WATERMARK_INGRESS_INSPECT", "true").lower() in ("1", "true", "yes")
    WATERMARK_IMAGE_STRIP_UPLOADS: bool = os.getenv("WATERMARK_IMAGE_STRIP_UPLOADS", "true").lower() in ("1", "true", "yes")
    WATERMARK_IMAGE_STRIP_GENERATED: bool = os.getenv("WATERMARK_IMAGE_STRIP_GENERATED", "true").lower() in ("1", "true", "yes")
    WATERMARK_LAYER_B_ENABLED: bool = os.getenv("WATERMARK_LAYER_B_ENABLED", "true").lower() in ("1", "true", "yes")
    WATERMARK_LAYER_B_STRATEGY: str = os.getenv("WATERMARK_LAYER_B_STRATEGY", "paraphrase")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS env var into a list of origin strings."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()

# A denylist/AST guard cannot safely contain LLM-generated code on the API host.
# Fail closed rather than allowing a deployment to opt into the legacy
# subprocess executor accidentally through a copied environment file. The
# isolated container sandbox (mode="container") is the only path permitted
# in production; it's still gated separately at runtime by a Docker/image
# health check (application/flows/services.py:_init_executor) before code
# execution is actually wired in.
if settings.ENVIRONMENT == "production" and settings.EXEC_SANDBOX_ENABLED:
    if settings.EXEC_SANDBOX_MODE != "container":
        raise RuntimeError(
            f"EXEC_SANDBOX_MODE={settings.EXEC_SANDBOX_MODE!r} is not permitted in "
            "production with EXEC_SANDBOX_ENABLED=true. Only the isolated "
            "container sandbox (EXEC_SANDBOX_MODE=container) may run in production."
        )
    if not settings.SANDBOX_WORKER_TOKEN:
        raise RuntimeError(
            "SANDBOX_WORKER_TOKEN must be set when EXEC_SANDBOX_ENABLED=true "
            "in production — an unauthenticated sandbox worker cannot be trusted."
        )

# Fail fast at startup if CSRF protection is enabled but no secret is configured.
if settings.CSRF_ENFORCE_BACKEND and not settings.CSRF_SECRET:
    raise RuntimeError(
        "CSRF_SECRET environment variable must be set when CSRF_ENFORCE_BACKEND=true. "
        "Set CSRF_ENFORCE_BACKEND=false to disable CSRF protection (development only)."
    )

if settings.ENVIRONMENT == "production":
    for secret_name in ("CSRF_SECRET", "ADMIN_API_KEY"):
        secret_value = getattr(settings, secret_name) or ""
        if len(secret_value) < 32:
            raise RuntimeError(
                f"{secret_name} must be configured with at least 32 characters in production."
            )
    if settings.JWT_SECRET_KEY and len(settings.JWT_SECRET_KEY) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters in production.")
