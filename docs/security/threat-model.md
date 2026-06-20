# Reasoner Threat Model (STRIDE)

**Version**: v1.0 — 2026-06-02
**Scope**: Reasoner v3.0 architecture (post-refactoring)
**Methodology**: STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege)

---

## Trust Boundaries

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Browser UI  │────▶│  Next.js API  │────▶│  FastAPI       │
│  (untrusted) │     │  (proxy)      │     │  (trusted)     │
└─────────────┘     └──────────────┘     └───────────────┘
                                                 │
                              ┌──────────────────┼──────────────────┐
                              ▼                  ▼                  ▼
                     ┌────────────┐    ┌────────────┐    ┌────────────┐
                     │  LLM APIs  │    │  SearXNG    │    │  Database  │
                     │  (external)│    │  (internal) │    │  (internal)│
                     └────────────┘    └────────────┘    └────────────┘
```

Trust boundaries:
1. **Browser → Next.js**: Unauthenticated/unauthenticated boundary
2. **Next.js → FastAPI**: Internal proxy; validated by port allowlist
3. **FastAPI → LLM APIs**: External service; API key auth
4. **FastAPI → SearXNG**: Internal service; Docker network
5. **FastAPI → Postgres/Redis**: Internal service; connection auth

---

## STRIDE Analysis

### 1. Spoofing

| Threat | Asset | Risk | Mitigation | Status |
|--------|-------|------|------------|--------|
| Fake JWT token | User sessions | High | Supabase JWT verification; HMAC if local fallback | ✅ Implemented |
| Spoofed admin requests | Admin endpoints | High | Dual auth: JWT admin scope + X-Admin-Key header; `secrets.compare_digest()` | ✅ Implemented |
| Fake CSRF token | State-changing requests | Medium | HMAC-SHA256 signed tokens; verified in Next.js and FastAPI | ✅ Implemented |
| API key theft via logs | LLM API keys | High | `SafeLoggingFilter` redacts keys from all log output | ✅ Implemented |
| Impersonated provider response | LLM responses | Low | Circuit breaker + fallback chain limits damage from bad responses | ⚠️ Partial |

### 2. Tampering

| Threat | Asset | Risk | Mitigation | Status |
|--------|-------|------|------------|--------|
| Prompt injection | Pipeline integrity | High | `sanitize_for_prompt()` with layered filtering; XSS prevention | ✅ Implemented |
| Malicious uploaded files | Server/DB | Medium | File type detection via `python-magic`; size limits | ✅ Implemented |
| SSE stream modification | Real-time UI | Low | SSE via HTTPS; proxy in Next.js validates upstream | ✅ Implemented |
| State file corruption | Pipeline resumption | Low | JSON schema validation in `_from_dict` with defensive `.get()` | ✅ Implemented |
| Database row tampering | User data | Medium | PostgreSQL row-level security not yet configured | ❌ Not implemented |

### 3. Repudiation

| Threat | Asset | Risk | Mitigation | Status |
|--------|-------|------|------------|--------|
| No audit trail for pipeline runs | Compliance | Medium | EventStore with append-only events; history entries in JSON | ✅ Implemented |
| Unauthenticated pipeline execution | Abuse tracking | Low | Optional auth; rate limiting by IP for unauthenticated users | ⚠️ Partial |
| Admin actions not logged | Audit compliance | Medium | AuditMiddleware logs all admin requests | ✅ Implemented |

### 4. Information Disclosure

| Threat | Asset | Risk | Mitigation | Status |
|--------|-------|------|------------|--------|
| API key in error messages | LLM credentials | High | `SafeLoggingFilter` redacts; error messages truncated to 120 chars | ✅ Implemented |
| Stack traces in production | System internals | Medium | Global exception handler in `api/error_handler.py`; Sentry captures internals safely | ✅ Implemented |
| Health endpoint leaking details | System topology | Low | Public response omits memory/DB details; admin key required for full output | ✅ Implemented |
| CORS misconfiguration | CSRF attack surface | Medium | `CORS_ORIGINS` env var; development mode warns but doesn't block | ⚠️ Dev-only risk |
| Configuration leakage via env bypass | API keys in `.env` | High | Consolidated to single `core/settings.py` reader; `os.environ` bypasses eliminated | ✅ Implemented |

### 5. Denial of Service

| Threat | Asset | Risk | Mitigation | Status |
|--------|-------|------|------------|--------|
| Rate limit exhaustion | API availability | High | Token-bucket rate limiter per IP/user; Redis backend for multi-worker | ✅ Implemented |
| LLM cost exhaustion | Budget | High | Per-phase token budgets; circuit breaker stops cascading failures | ✅ Implemented |
| Memory exhaustion | Process health | Medium | `MEMORY_LIMIT_MB` env var; `MemoryLimitMiddleware` with psutil monitoring | ✅ Implemented |
| Request timeout abuse | Resource starvation | Medium | `REQUEST_TIMEOUT_SECONDS` env var; `RequestTimeoutMiddleware` | ✅ Implemented |
| Dead-letter queue overflow | Event bus memory | Low | EventBus backpressure limit (1000 max); oldest events dropped if exceeded | ✅ Implemented |
| Connection pool exhaustion | Database | Low | DB_POOL_SIZE configurable; health check monitors pool stats | ✅ Implemented |

### 6. Elevation of Privilege

| Threat | Asset | Risk | Mitigation | Status |
|--------|-------|------|------------|--------|
| Admin endpoint access without key | System control | High | Dual auth: JWT admin scope + `X-Admin-Key`; `secrets.compare_digest()` | ✅ Implemented |
| Tier bypass via force_pipeline flag | Premium features | Medium | Preset tier enforcement in `require_tier` dependency | ⚠️ Placeholder (fails closed in prod) |
| Legacy API key abuse | Auth bypass | Low | `ENABLE_LEGACY_API_KEY` disabled by default; migration path documented | ✅ Implemented |
| Path traversal in save/load | File system | Low | `Path(path).parts` traversal check in `PipelineState.save()` and `.load()` | ✅ Implemented |
| Dependency vulnerability | Supply chain | Medium | `pip-audit` in CI; scheduled nightly scans | ✅ Implemented (Phase 4.4) |

---

## Risk Summary

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 0 | — |
| High | 7 | 6 implemented, 1 partial |
| Medium | 8 | 5 implemented, 2 partial, 1 not implemented |
| Low | 7 | 6 implemented, 1 partial |

## Open Items

1. **Tier enforcement** (Medium): `require_tier()` fails closed in production. Needs actual subscription DB integration (tracked as #501).
2. **Quota enforcement** (Medium): `check_quota()` uses conservative defaults. Needs tier-per-user DB (tracked as #502).
3. **PostgreSQL RLS** (Medium): Row-level security not configured. Mitigated by connection-string auth, but defense-in-depth recommended.
4. **Provider response authenticity** (Low): No cryptographic verification of LLM responses. Circuit breaker mitigates via fallback chain.

## Security Architecture Review Cadence

- Threat model reviewed at each major version increment
- Dependency scan runs nightly via CI cron
- Code changes to auth/settings/sanitization require security review
