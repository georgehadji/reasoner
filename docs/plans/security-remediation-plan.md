# Security Remediation Plan

## Objective and architecture principles

Remediate the 2026-08-16 audit without eroding Reasoner’s layered architecture:

1. **Core/domain remain pure.** Security policy is expressed as ports, value objects,
   commands, and domain decisions; no FastAPI, filesystem, Docker, or provider imports.
2. **Application services orchestrate policy.** They own use-case sequencing, authorization
   decisions, idempotency, quota reservation, and auditing.
3. **Infrastructure adapters enforce physical controls.** Containers, storage ACLs, rate
   backends, and provider clients live here.
4. **API and Next.js are adapters, not policy owners.** They authenticate requests, map them
   to commands, and serialize safe responses. Backend authorization is authoritative.
5. **Deny by default and fail closed.** Missing ownership, unavailable policy data, unknown
   file IDs, invalid origins, and unavailable quotas deny the operation.

## Delivery order

### Phase 0 — Contain critical execution risk (immediate)

**Goal:** No LLM-produced code executes on the application host.

1. Add `CODE_EXECUTION_ENABLED=false` to `core/settings.py`, defaulting to false in every
   environment except explicit integration tests.
2. Change `PipelineWorkflowServices` construction to use `NoopExecutor` unless an approved
   isolated executor adapter is configured.
3. Remove `pickle`, `pathlib`, `io`, and `os.path` from the current allowlist. Treat the AST
   check as a user-experience filter only; do not advertise it as sandboxing.
4. Block enabling code execution in production unless an `ExecutionSandboxPort` adapter
   passes startup health checks.
5. Add an operational kill switch and an audit event for every attempted code execution.

**Pattern:** Feature flag + Null Object (`NoopExecutor`) + port/adapter.

**Acceptance criteria:**

- No production code path instantiates `SubprocessExecutor` by default.
- A malicious `Path.write_text` or pickle payload is rejected before process creation.
- Tests prove the default executor never creates a subprocess.

### Phase 1 — Build a real isolated execution boundary

**Goal:** Reintroduce code execution only behind a defensible isolation boundary.

1. Define `ExecutionSandboxPort` in `core/ports/` with `execute(ExecutionRequest) ->
   ExecutionResult`. Keep language, timeout, memory, output, and policy version explicit.
2. Implement `ContainerExecutionSandbox` in `infrastructure/execution/` using an external
   per-job container runtime/service. The runner must use:

   - non-root UID and read-only root filesystem;
   - no host bind mounts or Docker socket;
   - network namespace disabled;
   - dropped Linux capabilities and `no-new-privileges`;
   - seccomp/AppArmor or equivalent sandbox profile;
   - CPU, memory, PID, file-size, and wall-clock limits;
   - ephemeral working storage deleted by the runtime.

3. Place the executor in a separate deployment/service account, not the API container. Use a
   request/response queue or narrowly authenticated internal API. Never accept arbitrary
   image names, commands, mounts, environment variables, or runtime options from callers.
4. Use a Strategy pattern for language runners (`PythonRunner`, future `JavaScriptRunner`) and
   an Adapter for the chosen container platform. Keep the application service independent of
   Docker/Kubernetes specifics.
5. Emit `CodeExecutionRequested`, `CodeExecutionCompleted`, and
   `CodeExecutionRejected` domain events with non-sensitive metadata only.

**Acceptance criteria:**

- Escape tests cannot read/write a sentinel outside the job workspace.
- The worker has no credentials, database access, or network route to private services.
- Security integration tests run against the actual sandbox, not only an AST guard.

### Phase 2 — Centralize metering and authorization

**Goal:** Every costly use case has one authoritative policy path.

1. Add a `MeteredOperation` application service/decorator around a command handler. It should
   perform, in order: authenticate principal, authorize capability, reserve credits, execute,
   settle actual usage, and release/refund on safe failure.
2. Model actions as capabilities (for example `pipeline.run`, `image.generate`,
   `context.run`, `cache.invalidate`) in the domain. Avoid scattered boolean checks.
3. Route `/api/run`, `/api/run-with-context`, image generation, agent runs, and future tools
   through the same application command handler. API handlers only construct commands.
4. Require authentication for all metered work in production. If an anonymous trial is a
   product requirement, make it an explicit `AnonymousTrialPolicy` with low, server-side
   daily limits, abuse controls, zero access to uploads/history, and a capped spend ledger.
5. Ensure account API keys map to a canonical user and capability set before metering.

**Pattern:** Command Handler + Decorator/Policy object + Unit of Work for reservation/settlement.

**Acceptance criteria:**

- It is impossible to add a provider-costing route without selecting an authorization and
  metering policy.
- Anonymous requests to image/context execution receive 401 in production.
- Concurrent requests cannot overspend a user balance.

### Phase 3 — Secure real-time pipeline access

**Goal:** WebSockets are authenticated, origin-checked, tenant-bound, and observable without
revealing tenant data.

1. Define a `WebSocketSession` value object containing principal ID, auth method, validated
   origin, issued-at time, and connection ID.
2. Require a short-lived, single-purpose WebSocket ticket obtained from an authenticated
   HTTPS endpoint. Do not use access tokens in query strings; browsers should send the ticket
   through the subprotocol or first authenticated message, then discard it.
3. Add an `OriginPolicyPort` and enforce it before accepting the socket. Apply IP/principal
   connection and message-rate limits through the existing rate-limiter port.
4. Change `WebSocketManager.subscribe` to receive a principal and call a centralized
   `PipelineAccessPolicy`. Anonymous pipelines should either be private to an opaque,
   unguessable owner session or not support WebSocket replay.
5. Replace public detailed stats with an administrator-only aggregate metrics endpoint; never
   return pipeline IDs.

**Pattern:** Session capability token + Policy Enforcement Point + Observer for metrics.

**Acceptance criteria:**

- Missing/invalid ticket and unapproved Origin are rejected before `accept()`.
- One user cannot subscribe to another user’s or anonymous pipeline.
- Connection flooding is bounded and emits metrics without logging credentials.

### Phase 4 — Make documents tenant-safe and resource-bounded

**Goal:** Upload, extraction, and semantic retrieval consistently preserve tenant isolation.

1. Introduce a `DocumentRepository` application port with principal-aware methods:
   `create`, `list`, `get_text`, `authorize_ids`, `delete`, and `get_index_reference`.
2. Store documents under tenant-scoped storage keys and enforce ownership in the repository,
   rather than allowing infrastructure callers to access a file ID directly.
3. Make content deduplication tenant-scoped. If cross-tenant deduplication is needed later,
   use a privacy-reviewed, non-observable content-addressing service that never exposes another
   tenant’s ID or existence.
4. Have `DocumentVectorStore` receive authorized document references rather than raw file IDs.
   Persist vectors with tenant metadata and enforce it at retrieval time.
5. Add an `UploadPolicy` with maximum request bytes, file count, storage quota, MIME signature
   verification, parser limits, and extraction time budget. Stream to a quarantine location;
   promote only after validation.
6. Move PDF/DOCX/OCR extraction to a bounded worker queue. Apply backpressure and report job
   state via domain events rather than holding the API request open.
7. Encrypt uploaded originals, metadata, and vector sidecars at rest using the existing crypto
   port; minimize plaintext paths and user IDs in metadata.

**Pattern:** Repository + Capability-based reference + Producer/Consumer queue + State machine
(`quarantined -> validated -> extracted -> indexed -> failed`).

**Acceptance criteria:**

- Foreign document IDs produce a uniform not-found response and no retrieval occurs.
- A multipart request exceeding total bytes/file count is rejected before buffering all parts.
- Parser bomb tests cannot exhaust API-worker memory or CPU.

### Phase 5 — Harden administrative and public operational endpoints

**Goal:** Separate CSRF, authentication, authorization, and abuse resistance.

1. Create `require_admin_operation` as a shared FastAPI dependency backed by an application
   `AdminAuthorizationPolicy`. It validates a scoped principal and, where required, a distinct
   machine credential using constant-time comparison.
2. Move cache invalidation behind a `InvalidateCacheCommand`, authorize it as an admin
   capability, add narrow rate limits, and publish an audit event that contains scope/count but
   no cached content.
3. Apply backend request-size limits and rate limits to error/feedback ingestion. Define
   bounded Pydantic schemas for strings, stack traces, URLs, and metadata; store a digest for
   deduplication.
4. Make health endpoints return only a simple public readiness/liveness status. Put detailed
   dependency errors in authenticated diagnostics/logs.
5. Define an `UpstreamTargetPolicy` in the frontend/server proxy: canonicalize hostnames,
   resolve DNS immediately before use, reject loopback/private/link-local/multicast IPv4 and
   IPv6 addresses, prevent redirects, and retain a strict host allowlist for production.

**Pattern:** Policy objects + Command Handler + bounded DTOs + anti-corruption layer.

### Phase 6 — Deployment and supply-chain hardening

**Goal:** Reduce secret exposure and make security signals enforceable.

1. Split `.env` into service-specific secret inputs. The frontend receives only public
   Supabase configuration and its backend API target; it must not receive provider, database,
   encryption, admin, or payment secrets.
2. Use Docker/Kubernetes secrets or an external secret manager, mount credentials read-only,
   and rotate static admin credentials into managed, scoped machine identities where possible.
3. Configure Caddy internal upstream TLS with the internal CA and hostname verification; remove
   `tls_insecure_skip_verify`. Mount only each service’s own key/certificate.
4. Pin base images by digest and use an SBOM/image scan in CI. Pin Python dependencies through
   a generated lockfile with hashes and use `npm ci` from the committed lockfile.
5. Change security workflows to fail on secrets, critical/high advisories, and confirmed static
   findings. Allow suppression only through reviewed, expiring inline justification.
6. Add Dependabot/Renovate with grouped, test-gated updates and a scheduled authenticated
   `pip-audit`/`npm audit` report.

**Pattern:** Least privilege + immutable build + policy-as-code.

## Test strategy

Add regression tests alongside each boundary:

- Unit tests for capability, ownership, origin, upload, and metering policy decisions.
- API tests proving every metered endpoint rejects unauthenticated production callers.
- WebSocket integration tests for handshake Origin/auth failure, cross-user subscription, and
  connection rate limits.
- Sandbox integration tests for filesystem, process, network, deserialization, resource, and
  cleanup escape attempts.
- Property/fuzz tests for upload MIME/path/ID handling and upstream URL normalization.
- Contract tests ensuring Next proxy and FastAPI routes use the same authorization semantics.
- Deployment tests that assert secret allowlists and verified internal TLS.

## Rollout and governance

1. Deploy Phase 0 as an emergency patch and verify no execution jobs are running.
2. Land phases 2–5 behind feature flags with metrics for rejects, rate limits, denied document
   access, and credit reservation failures.
3. Migrate document ownership metadata before enabling the new repository as authoritative;
   fail closed for un-migrated records.
4. Run a staging adversarial test suite, then a focused external penetration test of sandbox,
   WebSocket, upload, and tenant-isolation boundaries.
5. Require security review for future provider-costing routes, new file types, new real-time
   protocols, and new execution languages.
