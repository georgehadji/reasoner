# Reasoner Security Audit

**Date:** 2026-08-16  
**Scope:** Backend API, authentication and authorization, WebSockets, file handling,
code execution, frontend proxy layer, deployment configuration, and CI security controls.  
**Method:** Read-only code review, targeted static analysis, and a non-executing
sandbox-policy validation. No secrets or `.env` values were inspected.

## Executive summary

Reasoner has several sound controls: production-local-auth prevention, parameterized
database queries, CSRF signing, trusted-proxy-aware IP parsing, route-level ownership
checks, security headers, and a frontend proxy header allowlist. The principal risk is
that the code-execution feature relies on an AST denylist while running LLM-produced
Python on the application host. That is not a security boundary.

Four issues require priority remediation before exposing the affected capabilities to
untrusted users: host code execution, anonymous access to metered endpoints,
unauthenticated/weakly protected WebSockets, and upload-related resource exhaustion.

## Findings

### SEC-001 — Critical: LLM-generated code can read/write the application host

**Affected code**

- `src/reasoner/core/exec_constants.py`
- `src/reasoner/core/code_safety.py`
- `src/reasoner/infrastructure/execution/subprocess_executor.py`
- `src/reasoner/application/flows/cognitive_phases.py`

`SubprocessExecutor` executes LLM-generated Program-of-Thought and coding-validation
code as the application user. `EXEC_IMPORT_ALLOWLIST` permits `pathlib`, `io`, and
`pickle`; the AST policy blocks only selected function names. Consequently,
`Path(...).read_text()`, `Path(...).write_text(...)`, and `pickle.loads(...)` pass the
guard. The audit validated that each is classified `SAFE` without executing the code.

`pickle.loads` can invoke arbitrary code while deserializing attacker-controlled bytes.
Even without pickle, `pathlib` allows access to the host filesystem. In the Docker image,
the application user owns `/app`, including mounted runtime directories.

**Impact:** Remote code execution and potential disclosure or destruction of application
data and credentials if an attacker can influence model-produced code.

**Required remediation:** Replace the in-process/host subprocess boundary with an
isolated execution service. Disable execution until that boundary is deployed. AST
validation may remain as an early rejection layer, but must never be treated as the
security boundary.

### SEC-002 — High: metered endpoints do not consistently require authentication

**Affected code**

- `src/reasoner/api/routes/images.py`
- `src/reasoner/api/routes/context.py`
- `src/reasoner/api/__init__.py`

`/api/run` explicitly rejects anonymous callers when legacy access is disabled. In
contrast, `/api/generate-image` and `/api/run-with-context` use optional authentication,
apply quota only if a user is present, and do not reserve credits. These routes can invoke
provider-backed work behind only anonymous IP rate limits.

**Impact:** Provider-cost abuse, quota bypass, and elevated availability risk.

**Required remediation:** Establish one application-level `MeteredRunPolicy` used by
every provider-costing route. It must require a principal, authorize the operation,
reserve credits atomically, and settle usage on completion/failure.

### SEC-003 — High: WebSocket admission and observability leak pipeline metadata

**Affected code**

- `src/reasoner/api/routes/websocket.py`
- `src/reasoner/infrastructure/websocket/manager.py`
- `src/reasoner/application/ports/pipeline_ownership_port.py`

Socket connections are accepted when no token is supplied. The endpoints neither validate
`Origin` nor apply connection/message rate limits. `/api/websocket/stats` is public and
returns subscribed pipeline IDs. Explicitly anonymous pipeline records are authorized for
an unauthenticated caller once the ID is known.

**Impact:** Exposure of anonymous run progress/results, pipeline-ID disclosure, and
connection-exhaustion attacks.

**Required remediation:** Require authenticated WebSocket principals, authorize every
subscription against the ownership port, validate Origin at handshake, remove query-string
tokens, and restrict operational statistics to administrators.

### SEC-004 — High: upload handling permits large aggregate memory and parser DoS

**Affected code**

- `src/reasoner/api/routes/uploads.py`
- `src/reasoner/infrastructure/uploader.py`

The route reads each multipart part into memory, permits 50 MB per file, and sets no
file-count or request-total limit. PDF/DOCX parsing and OCR do not enforce parser-level
resource budgets.

**Impact:** A small number of authenticated requests can exhaust memory, disk, worker
capacity, and external OCR/model budget.

**Required remediation:** Enforce request and part limits at Caddy/ASGI/application
layers; stream uploads to bounded temporary storage; cap file count; use a dedicated,
resource-limited extraction worker; and impose page, object, decompression, and execution
time limits.

### SEC-005 — Medium: CSRF protects a global cache deletion route that lacks authorization

**Affected code**

- `src/reasoner/api/__init__.py`
- `src/reasoner/api/auth_deps.py`

`DELETE /api/cache` requires a CSRF token but no authenticated principal or administrator
permission. The token issuance endpoint is anonymous. CSRF establishes request origin
properties, not caller authorization, so a direct client can obtain a token and clear the
shared cache.

**Impact:** Availability degradation and cache-thrashing.

**Required remediation:** Require an admin principal and admin capability; add a narrow
rate limit and an auditable cache-invalidation command.

### SEC-006 — Medium: document-vector retrieval is not tenant-authorized

**Affected code**

- `src/reasoner/infrastructure/uploader.py`
- `src/reasoner/api/execution/pipeline.py`
- `src/reasoner/infrastructure/prism/file_search.py`
- `src/reasoner/documents/vector_store.py`

Upload deduplication is global and returns an existing file ID before an ownership check.
Pipeline requests accept file IDs and vector-search implementations load sidecars directly
without verifying that the current user owns each ID.

**Impact:** Cross-tenant retrieval if a file ID is exposed or guessed; global deduplication
also creates an upload-existence oracle.

**Required remediation:** Make deduplication tenant-scoped and introduce an authorized
`DocumentRepository` port that resolves IDs for a principal before extraction, indexing, or
retrieval.

### SEC-007 — Medium: deployment has excessive secret distribution and disabled TLS verification

**Affected code**

- `docker-compose.yml`
- `Caddyfile`
- `Caddyfile.prod`

The frontend receives the repository-wide `.env`, exposing server-only secrets to the
frontend process. Caddy disables verification of every internal TLS upstream with
`tls_insecure_skip_verify`.

**Impact:** Larger blast radius from frontend compromise and susceptibility to internal
network interception/misrouting.

**Required remediation:** Split environment files by service, mount only needed secrets,
and configure Caddy to trust and verify the internal CA/SANs.

### SEC-008 — Medium: security controls are non-blocking in CI

**Affected code**

- `.github/workflows/security.yml`
- `requirements.txt`

`pip-audit`, Bandit, and `npm audit` are followed by `|| true`, so CI always succeeds
after a vulnerability report. Python production dependencies are broad ranges without a
lockfile or hash verification.

**Impact:** Known vulnerabilities can be merged and builds are not reproducible.

**Required remediation:** Make policy violations fail CI, use pinned lockfiles with hashes,
and adopt scheduled dependency-update pull requests with review gates.

### SEC-009 — Medium: administrator authorization is inconsistent

**Affected code**

- `src/reasoner/api/routes/admin.py`
- `src/reasoner/api/routes/feedback.py`
- `src/reasoner/api/routes/errors.py`

Some admin endpoints require only `X-Admin-Key`; others require both the static key and an
authenticated administrator scope. This differs from the project’s documented control.

**Impact:** A single credential has broader power than the intended defense-in-depth model.

**Required remediation:** Centralize administrator authorization behind one FastAPI
dependency that validates both a scoped principal and a separately managed service/admin
credential where machine-to-machine access is required.

## Additional hardening observations

- Backend `/api/error-report` lacks backend-side request-size and rate controls; the Next.js
  proxy limit is bypassed by direct backend traffic.
- Public health responses include raw dependency exception text.
- Upstream URL validation should resolve hostnames and reject IPv6, IPv4-mapped, and DNS
  rebinding paths to private/link-local addresses.
- The API CSP still permits inline script; the separate Next.js CSP is stronger.

## Validation and limitations

- Targeted Bandit scan found 29 results: 25 low-severity exception-control-flow warnings;
  four SQL warnings were false positives because the interpolated identifiers are fixed
  allowlists and values use `$1` parameters.
- Sandbox-policy validation confirmed `pathlib` read/write and `pickle.loads` are accepted
  as `SAFE` by the current guard.
- A selected pytest batch and the npm advisory query timed out in the local environment.
  The findings above are code-path findings and do not depend on either result.
