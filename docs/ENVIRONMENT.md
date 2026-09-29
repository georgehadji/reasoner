# Environment Variables

## Core LLM

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Primary LLM access key |
| `OPENAI_API_KEY` | — | Direct OpenAI access |
| `ANTHROPIC_API_KEY` | — | Direct Anthropic access |
| `GOOGLE_API_KEY` | — | Google Gemini access |
| `DEEPSEEK_API_KEY` | — | DeepSeek access |
| `MISTRAL_API_KEY` | — | Mistral access |
| `XAI_API_KEY` | — | xAI Grok access |
| `PERPLEXITY_API_KEY` | — | Perplexity Sonar access |
| `DASHSCOPE_API_KEY` | — | Alibaba Qwen access |
| `MOONSHOT_API_KEY` | — | Moonshot Kimi access |
| `ZHIPUAI_API_KEY` | — | ZhipuAI GLM access |

## Jev (HyperGate routing)

TypeSafe's jev, a System One decision model, answers HyperGate's routing
questions (direct? web search? how complex? which method?) in one ~0.5s call.
Uses `OPENROUTER_API_KEY` (OpenRouter's `/api/v1/systemone` endpoint); no
TypeSafe account or key. See `src/reasoner/hypergate/jev_router.py`.

**Any mode but `off` sends each problem's text to TypeSafe via OpenRouter** — a
sub-processor. Log lines carry a hash of the problem, never its text.

| Variable | Default | Description |
|---|---|---|
| `JEV_MODE` | `active` | `active`: jev routes; HyperGate's LLM sub-agents run only when jev fails, times out, or answers below the confidence gate (`JEV_ACCEPT_*` in `core/constants_limits.py`). Each decision is logged as `jev_route {...}`. `shadow`: the LLM sub-agents route and jev is logged beside them as `jev_shadow {...}`. `off`: jev is never called — **the kill switch**. Anything else reads as `off`. Needs `OPENROUTER_API_KEY`; without it jev stays off and startup logs a warning |
| `JEV_MODEL` | `typesafe/jev-1.13` | Pinned model id. The served id is a dated snapshot and is logged per call |

The confidence gate's thresholds are initial values, not measured ones. Tune
them from the `jev_route` lines: `source` says who routed, `reason` why jev was
or wasn't used, and `agree_route` whether jev's declined verdict matched the
LLMs'.

`JEV_MODE` also governs the **iterative-critique critic**
(`application/flows/iterative_critique_phases.py`). In `active`, jev scores each
round's answer on the critic's four dimensions; if every one reaches the
critic prompt's own ACCEPT bar (`ACCEPT_SCORE` in `phases/iterative_critique.py`,
8/10) the round is accepted and the LLM critic is skipped, otherwise the LLM
critic runs as before and writes the flaws the next revision needs. Rounds whose
problem + answer exceed 8000 characters skip jev rather than truncate. Logged
as `jev_ic {...}`; `agree_accept` (shadow mode) says whether jev's accept call
matched the LLM critic's verdict. This sends model-written answers, not just the
user's problem, to TypeSafe.

## Search

| Variable | Default | Description |
|---|---|---|
| `SEARXNG_URL` | `http://localhost:8888` | SearXNG instance URL |
| `SEARXNG_SECRET_KEY` | — | SearXNG secret key |

## Server

| Variable | Default | Description |
|---|---|---|
| `SERVER_HOST` | `127.0.0.1` | FastAPI bind host |
| `SERVER_PORT` | `8000` | FastAPI bind port |
| `UVICORN_HOST` | `127.0.0.1` | Uvicorn bind host |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated allowed origins |

## Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `DB_POOL_SIZE` | `10` | `asyncpg` connection pool max size |

## Rate Limiting & Auth

| Variable | Default | Description |
|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | `60` | Per-minute request limit |
| `RATE_LIMIT_PER_HOUR` | `1000` | Per-hour request limit |
| `RATE_LIMIT_BURST` | `10` | Burst allowance |
| `ADMIN_API_KEY` | — | Admin endpoint key |
| `AUTH_PERSISTENCE_ENABLED` | `false` | Persist auth keys to DB |
| `AUTH_DB_PATH` | `src/reasoner/auth_keys.db` | SQLite auth DB path |

## CSRF & Security

| Variable | Default | Description |
|---|---|---|
| `CSRF_SECRET` | — | HMAC secret for CSRF tokens |
| `CSRF_ENFORCE_BACKEND` | `true` | Require CSRF on state-changing ops |

## VS (Verbalized Sampling)

| Variable | Default | Description |
|---|---|---|
| `VS_PROBE_GENERATION_ENABLED` | `true` | Enable probe generation stage |
| `VS_DECOMPOSITION_ENABLED` | `true` | Enable VS decomposition stage |
| `VS_COVERAGE_AUDIT_ENABLED` | `true` | Enable coverage audit stage |
| `VS_GENERATION_ENABLED` | `true` | Enable VS generation stage |
| `VS_CALIBRATION_ENABLED` | `true` | Enable calibration stage |
| `VS_CLAIM_EXTRACTION_ENABLED` | `true` | Enable claim extraction stage |
| `VS_VERIFICATION_ROUTING_ENABLED` | `true` | Enable verification routing |
| `VS_CONFLICT_SURFACING_ENABLED` | `true` | Enable conflict surfacing |
| `VS_BEHAVIORAL_AUDIT_ENABLED` | `true` | Enable behavioral audit |

All VS flags are controlled via `VSFeatureFlags` in code; env vars are not yet wired.

## Neuro Memory

| Variable | Default | Description |
|---|---|---|
| `NEURO_REASONING_MODEL` | `openai/gpt-4o-mini` | Model for Neuro recall/learn |
| `NEURO_EMBEDDING_MODEL` | `qwen/qwen3-embedding-8b` | Embedding model for Neuro |

## Other

| Variable | Default | Description |
|---|---|---|
| `COHERE_RERANK_ENABLED` | `true` | Enable Cohere reranking |
| `DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED` | `false` | Semantic retrieval for uploads |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Sentry sampling rate |
| `DEBUG` | `false` | Debug mode |
| `LOG_LEVEL` | `INFO` | Logging level |
