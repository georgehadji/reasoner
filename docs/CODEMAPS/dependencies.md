<!-- Generated: 2026-06-08 | Files scanned: 375 | Token estimate: ~650 -->

# Dependencies & Integrations

## External Services

| Service | Purpose | Integration |
|---------|---------|-------------|
| OpenRouter | Primary LLM routing (350+ models) | infrastructure/llm/providers/openai_compat.py |
| Anthropic | Direct Claude adapter | anthropic SDK |
| OpenAI | Direct GPT adapter + image gen | openai SDK |
| Google AI | Direct Gemini adapter | google-genai SDK |
| Perplexity | Direct + Sonar search | HTTP via httpx |
| DeepSeek | Direct adapter | OpenAI-compat |
| Mistral | Direct adapter | OpenAI-compat |
| xAI (Grok) | Direct adapter | OpenAI-compat |
| Qwen | Direct adapter | OpenAI-compat |
| Kimi | Direct adapter | OpenAI-compat |
| GLM | Direct adapter | OpenAI-compat |
| MiniMax | Direct adapter | OpenAI-compat |
| Ollama | Local model adapter | OpenAI-compat |
| SearXNG | Web search (self-hosted Docker) | core/search.py |
| Supabase | Auth (production) + DB | supabase SDK + asyncpg |
| Stripe | Billing / subscriptions | stripe SDK, infrastructure/billing/ |
| Redis | Session state cache | redis SDK, infrastructure/redis/ |
| DeepL | Translation | infrastructure/translation/deepl_client.py |
| Sentry | Error monitoring (frontend) | @sentry/nextjs |

## LLM Provider Architecture
```
infrastructure/llm/registry.py   → _MODEL_WHITELIST (90+ models), build_provider()
infrastructure/llm/router.py     → ProviderRouter: role-based routing, fallback chain
infrastructure/llm/ports.py      → LLMProvider Protocol, Message, LLMResponse
infrastructure/llm/base.py       → shared base provider logic
infrastructure/llm/providers/openai_compat.py → OpenAI-compatible adapter (covers 12 providers)
infrastructure/llm/image_generation.py → image gen via OpenAI/compatible
infrastructure/llm/extraction/   → vision LLM OCR / image description
```

## Model Whitelist Highlights (90+ models)
Budget → Balanced → Premium per method. Cross-lab diversity enforced:
- Phase 2 generators: ≥3 labs (Budget), ≥4 labs (Premium)
- Scorer: different ecosystem than dominant generator
- Fallback: cross-lab equivalent, never blindly to preset primary

## Python Backend Dependencies
```
# Core
fastapi>=0.109,<0.116    uvicorn[standard]    pydantic>=2.6
httpx>=0.27              python-multipart

# LLM SDKs
anthropic>=0.18          openai>=1.12         google-genai>=1.0

# Auth / SaaS
supabase>=2.0            PyJWT>=2.8           stripe>=12.0
redis>=5.0               asyncpg>=0.29

# Storage
aiosqlite>=0.19          sqlalchemy[asyncio]>=2.0    alembic>=1.13

# File processing
pypdf>=4.0               python-docx>=1.1     pymupdf>=1.23   python-magic>=0.4.27

# Utilities
python-dotenv>=1.0       simpleeval>=0.9.13   lxml>=5.1

# Finance widgets
yfinance>=0.2.36         yahooquery>=2.3
```

## Frontend Dependencies
```
# Framework
next@16.2.3              react@19.2.4         typescript^5

# Styling
tailwindcss^4            @tailwindcss/postcss^4    tailwind-merge^3
framer-motion^12         three^0.184          @types/three^0.184

# State / Data
zustand^5                swr^2                idb^8

# Auth / Payments
@supabase/supabase-js^2  @stripe/react-stripe-js^6   @stripe/stripe-js^9

# Markdown
react-markdown^10        react-syntax-highlighter^16   remark-gfm^4   rehype-highlight^7

# UI
lucide-react^1           next-themes^0.4      clsx^2          recharts^3

# Monitoring
@sentry/nextjs^10

# Testing
vitest^4                 @testing-library/react^16   @playwright/test^1.59
```

## Internal Service Wiring
```
Neuro LTM    → mounted as FastAPI sub-app at /neuro/*
Widgets      → infrastructure/widgets/registry.py dispatches by type
Auth         → local_adapter (dev) | supabase_adapter (prod)  via AuthPort
Billing      → stripe_adapter via BillingPort
Quota        → cached_quota_repo → postgres (prod) / SQLite (dev)
```

## Security Integrations
```
sanitization.py          → input sanitization, prompt-injection defense
ara_persuasion_defense.py → adversarial persuasion defense
security/url_validator.py → URL allow-list validation
circuit_breaker.py       → per-provider circuit breaker (auto-fallback)
rate_limiter.py          → token-bucket per client IP
```
