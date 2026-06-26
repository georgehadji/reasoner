# Reasoner — Reasonix knowledge base

## Stack
- **Backend:** Python 3.12+ / FastAPI 0.115 / Pydantic v2 / uvicorn
- **Frontend:** Next.js 16 / React 19 / TypeScript 5 / Tailwind CSS v4 / Zustand v5
- **Key deps:** OpenRouter (primary LLM), httpx, anthropic/openai/google-genai SDKs, stripe, SWR, idb v8, framer-motion

## Layout
- `src/reasoner/` — Python backend: `api/` (FastAPI+SSE), `application/` (CQRS), `pipeline.py` (orchestrator), `phases/` (19 prompt modules), `hypergate/` (5 sub-agent pre-router), `domain/` (preset registry), `infrastructure/` (LLM providers, persistence), `neuro/` (memory), `core/` (settings, constants), `healing/`
- `ui-next/src/` — Next.js App Router: `app/` (pages + API proxy routes), `components/`, `hooks/` (SSE streaming), `stores/` (Zustand), `lib/` (types, api-client, security)
- `tests/` — pytest suite (~190 files, conftest.py at root)

## Commands
- **Backend dev:** `uvicorn asgi:app --reload --host 0.0.0.0 --port 8003`
- **Frontend dev:** `cd ui-next && npm run dev`
- **All servers:** `python start_all.py`
- **Tests (Python):** `pytest tests/`
- **Tests (frontend):** `cd ui-next && npm test` (vitest), `npm run test:e2e` (Playwright)
- **Lint:** `ruff check src/` (Python), `cd ui-next && npm run lint` (TS)
- **Typecheck:** `mypy src/`

## Conventions
- Commits use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` prefixes
- Tailwind CSS v4: no `tailwind.config.ts` — config in `globals.css` via `@import "tailwindcss"`
- Python tests: `test_*.py` in `tests/`, named after module under test
- API proxy: Next.js routes at `ui-next/src/app/api/*/route.ts` validate+forward to `http://127.0.0.1:8003` (from `API_BASE_URL` in `ui-next/.env.local`)
- Frontend SSE: `usePipelineStream` hook wraps `fetchWithCsrf` + `readSSEStream`
- Rate limiter: `RATE_LIMITER_MODE=memory` in dev `.env`; switch to `redis` for multi-worker

## Watch out for
- **No pyproject.toml** — Python deps in `requirements.txt` only. Ruff/pytest config has no central file (ruff uses defaults, pytest uses `tests/conftest.py`).
- **`_ensure_fresh_preset_service()`** in `api/streaming.py` deletes+reimports modules on first pipeline run — can break inline interpreters. Affects any code path importing presets mid-request.
- **`QueryTimer` is undefined** in `api/__init__.py: _run_stream_with_metrics` — `try/except ImportError` was added so SSE streaming degrades gracefully; don't reintroduce hard import.
- **First SSE event yields AFTER preflight** — if orchestrator.preflight() hangs (HyperGate LLM calls or neuro recall), user sees empty spinner with no phase_start event.
- **Two layer ratelimit** — Next.js proxy (`ui-next/src/lib/security-server.ts`, 10 req/min per IP) AND backend (`rate_limiter.py`, 10000/min with burst 50). Both must be tuned together.
- ARCHITECTURAL REAPER — DEEP AUDIT PROTOCOL V7## Senior Software Auditor: Blind Spot Discovery Engine

---

## ΠΡΟΑΠΑΙΤΟΥΜΕΝΑ (διάβασε πριν αρχίσεις)

### INPUT DECLARATION
Πριν ξεκινήσεις, δήλωσε τι έχεις στη διάθεσή σου:
- [ ] Source code (ποια directories/files)
- [ ] Architecture diagrams
- [ ] CI/CD config
- [ ] Dependency manifests (requirements.txt, package.json, etc.)
- [ ] Logs / metrics
- [ ] Interview με developer
- [ ] README / docs μόνο

**Αν ένα εύρημα βασίζεται σε έλλειψη evidence (δεν βλέπεις κώδικα), σήμανέ το ως [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] και εξήγησε τι χρειάζεσαι.**

### AUDIENCE
Δήλωσε σε ποιον απευθύνεσαι:
- **CTO/PM**: executive summary πρώτα, τεχνικές λεπτομέρειες σε παράρτημα
- **Tech Lead**: full technical depth
- **Security Officer**: Μέρη 5+10 πρωτεύουν
- **New Developer**: Μέρη 4+8 πρωτεύουν

### SCOPING (optional)
Αν θες audit μόνο συγκεκριμένων μερών, ορίσε:
`SCOPE: [1,5,7]` — τρέχει μόνο τα Μέρη 1, 5, 7

---

## ΘΕΜΕΛΙΩΔΕΙΣ ΚΑΝΟΝΕΣ

1. **Κάθε εύρημα: συγκεκριμένο αρχείο / συνάρτηση / config key.** Απαγορεύονται γενικές παρατηρήσεις.
2. **Αν δεν μπορείς να τεκμηριώσεις έναν ισχυρισμό:**
   - Σήμανέ τον ως `[ΕΙΚΑΣΙΑ]` + εξήγησε τι χρειάζεσαι για επιβεβαίωση
   - Σήμανέ τον ως `[ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ]` αν το evidence δεν σου δόθηκε
3. **Μην υποθέτεις ότι κάτι λειτουργεί επειδή δεν βλέπεις το αντίθετο.**
4. **Severity Rubric — ακολούθησε αυστηρά:**

| Level | Κριτήριο | Παραδείγματα |
|-------|----------|-------------|
| **P0** | Data loss / security breach / service down RIGHT NOW ή με trivial trigger | SQL injection, no auth, cascade delete χωρίς backup |
| **P1** | Θα συμβεί σε production εντός 30 ημερών υπό κανονική χρήση | Missing retry logic σε κρίσιμο path, token expiry χωρίς refresh |
| **P2** | Θα δημιουργήσει πρόβλημα σε scale ή edge case | Missing pagination, sync logging, connection pool unbounded |
| **P3** | Tech debt, best practice gap, δεν μπλοκάρει deployment | Outdated README, missing onboarding guide |

5. **Confidence Score** για κάθε εύρημα: `HIGH` (verified in code) / `MEDIUM` (inferred from pattern) / `LOW` (assumption without evidence).

---

## PRE-ANALYSIS: ΜΕΤΑ-ΕΛΕΓΧΟΙ

*Απάντησε αυτές ΠΡΙΝ τα findings — διαμορφώνουν το πώς βλέπεις το σύστημα:*

1. **Ανάστροφη αιτιότητα:** Μήπως αυτό που φαίνεται "αποτέλεσμα" είναι η αιτία;
2. **Επιβεβαιωτική προκατάληψη:** Έψαξα ενεργά στοιχεία που διαψεύδουν τις υποθέσεις μου;
3. **Άγνοια άγνοιας:** Τι δεν ξέρω ότι δεν ξέρω; (ποιά subsystems δεν έχω access)
4. **Survivorship bias:** Ποια bugs δεν έχουν εκδηλωθεί ακόμα και γι' αυτό δεν φαίνονται;
5. **Blast Radius Map:** Ποια components είναι connected; Αν το X πέσει, ποια άλλα σέρνει μαζί;

---

## ΜΕΡΟΣ 1: ΧΡΟΝΙΚΗ ΣΥΜΒΑΤΟΤΗΤΑ

**Depth Budget: 4 ευρήματα max — εστίασε στα πιο κρίσιμα**

### 1.1 Timezone & DST
- Αποθήκευση ημερομηνιών: UTC / τοπική / χωρίς timezone;
- Κεντρικό σημείο μετατροπής για εμφάνιση;
- Συμπεριφορά σε DST transitions (θερινή/χειμερινή ώρα);
- Ημερομηνίες pre-1970 / post-2038 (Unix overflow);

### 1.2 Λήξεις & Timeouts
- Tokens/sessions/passwords: λήξη + refresh mechanism;
- Database lock timeout behavior;
- External API call timeout + fallback;

### 1.3 Χρονικοί Συγχρονισμοί
- Scheduled tasks / cron: overlap behavior;
- Order-dependent operations χωρίς enforced ordering;
- NTP drift / clock change behavior;

**Output:**
| Εύρημα | Τοποθεσία | Σενάριο Αστοχίας | Severity | Confidence |
|--------|-----------|-----------------|---------|------------|

---

## ΜΕΡΟΣ 2: ΣΧΕΔΙΑΣΤΙΚΕΣ ΑΠΟΦΑΣΕΙΣ ΠΟΥ ΜΟΙΑΖΟΥΝ ΜΕ BUGS

**Depth Budget: 6 ευρήματα max**

### 2.1 Idempotency
- Ποιες λειτουργίες είναι idempotent; Τεκμηριωμένο;- POST /X δύο φορές: διπλό αποτέλεσμα;
- Deduplication layer: API / database / queue;

### 2.2 Delivery Semantics
- Exactly-once / at-least-once / at-most-once: δηλωμένο;
- Message queue duplicate handling;
- ACID transactions: πού ισχύουν, πού όχι;

### 2.3 Graceful Degradation
- Dependency failure: error ή degraded UX;
- Critical vs non-critical path διαχωρισμός;
- Fallback ανά εξωτερική υπηρεσία;

### 2.4 Backpressure
- Producer 10x faster than consumer: τι γίνεται;
- Queue overflow behavior;
- Rate limiting: gateway / app / database levels;

**Output:**
| Λειτουργία | Απόφαση | Τεκμ. (Ναι/Όχι) | Ρίσκο αν Παραβιαστεί | Severity | Confidence |
|-----------|---------|----------------|---------------------|---------|------------|

---

## ΜΕΡΟΣ 3: ΠΑΡΑΤΗΡΗΣΙΜΟΤΗΤΑ & ΚΟΣΤΟΣ

**Depth Budget: 5 ευρήματα max**
*(Αναλύεται ως 3 ξεχωριστοί pillars: Metrics | Logs | Traces + Alerting + Cost)*

### 3.1 Metrics
- Business KPIs υπάρχουν ή μόνο technical metrics (latency, error rate);
- Top 3 business metrics: παρακολουθούνται;
- Anomaly alerts σε business metrics;

### 3.2 Logs
- Structured logging (JSON) ή free-text;
- Log levels σωστά; Debug logs off σε production;
- Sensitive data σε logs (PII, secrets, tokens);
- Synchronous vs async logging;

### 3.3 Distributed Tracing
- Trace IDs διαπερνούν όλα τα services;
- Κενά στα spans;
- Correlation IDs σε async operations;

### 3.4 Alerting
- Alert fatigue: πόσα alerts είναι noise;
- Actionable alerts: κάθε alert έχει runbook;
- Dead man's switch για critical scheduled tasks;

### 3.5 Κόστος
- Κόστος ανά API call / operation;
- Monitoring κόστους υπάρχει;
- Resource limits (CPU/memory) + behavior at limit;

**Output:**
| Κατηγορία (Pillar) | Τρέχουσα Κατάσταση | Κενό | Επίπτωση | Severity | Confidence |
|-------------------|--------------------|------|----------|---------|------------|

---

## ΜΕΡΟΣ 4: ΑΝΘΡΩΠΙΝΟΙ ΠΑΡΑΓΟΝΤΕΣ

**Depth Budget: 4 ευρήματα max**

### 4.1 Μηνύματα Λάθους
- End user: information ή confusion;
- Developer logs: stack trace + context;
- Unique, searchable error codes;
- Information leakage (paths, queries, secrets);

### 4.2 Τεκμηρίωση
- README: ενημερωμένο ή museum artifact;
- Dev environment setup;
- Deployment + rollback procedures;
- Architecture decisions (ADRs);

### 4.3 Knowledge Concentration Risk
- "Bus factor": κομμάτια κώδικα που μόνο 1 άτομο καταλαβαίνει;
- Undocumented "danger zones";
- Αν ο expert φύγει: τι χάνεται;

### 4.4 Onboarding
- Time-to-first-commit για νέο developer;
- Onboarding guide: υπάρχει, ενημερωμένο;

**Output:**
| Περιοχή | Κενό | Επίπτωση | Severity | Confidence |
|---------|------|----------|---------|------------|

---

## ΜΕΡΟΣ 5: ΑΣΦΑΛΕΙΑ ΠΕΡΑ ΑΠΟ ΤΟ ΠΡΟΦΑΝΕΣ

**Depth Budget: 8 ευρήματα max**

### 5.1 Mass Assignment
- Αποδεκτά πεδία: whitelist ή blacklist;
- Validation σε όλα τα endpoints;

### 5.2 IDOR
- Authorization check σε κάθε resource access;
- IDs: predictable (auto-increment) ή random (UUID/ULID);

### 5.3 Race Conditions σε Authorization (TOCTOU)
- Role check: μόνο στην αρχή ή κατά τη διάρκεια;
- Role change mid-operation handling;

### 5.4 Side-Channel Leaks
- Timing attacks: response time αποκαλύπτει existence;
- Error message discrimination (user not found vs wrong password);
- Status codes as information leaks;

### 5.5 Secrets Management
- Secrets στον κώδικα / env vars / logs;
- Rotation mechanism: manual ή automated;
- Default credentials (admin/admin);

**Output:**
| Εύρημα | STRIDE Category | Attack Vector | Τρέχον Control | Κενό | Severity | Confidence |
|--------|----------------|--------------|---------------|------|---------|------------|

---

## ΜΕΡΟΣ 6: ΔΙΑΧΕΙΡΙΣΗ ΔΕΔΟΜΕΝΩΝ

**Depth Budget: 5 ευρήματα max**

### 6.1 Soft vs Hard Deletes
- Συνέπεια σε όλο το σύστημα;
- Soft-deleted data σε reports/analytics;
- GDPR right-to-erasure compliance;

### 6.2 Data Retention
- Log retention: compliant;
- Personal data retention policy;
- Automated vs manual deletion;

### 6.3 Cascading Deletes
- Delete user → τι γίνεται με related data;
- Foreign keys: ON DELETE CASCADE vs RESTRICT;
- Σκόπιμο ή ατύχημα;

### 6.4 Migration Safety
- Reversible migrations;
- Destructive operations (DROP, DELETE): warning process;
- Zero-downtime migration strategy;
- Mid-migration failure handling;

**Output:**
| Περιοχή | Τρέχουσα Συμπεριφορά | Ρίσκο | Severity | Confidence |
|---------|---------------------|-------|---------|------------|

---

## ΜΕΡΟΣ 7: ΑΝΤΙΜΕΤΩΠΙΣΗ ΑΣΤΟΧΙΑΣ ΣΕ ΒΑΘΟΣ

**Depth Budget: 6 ευρήματα max**

### 7.1 Retry Storms
- Retries με exponential backoff + jitter;
- Max retry count;
- Circuit breaker: threshold / timeout / half-open;

### 7.2 Poison Messages
- Message που προκαλεί crash: ξαναμπαίνει στην ουρά;
- Dead letter queue: υπάρχει + monitoring;

### 7.3 Partial Success
- Batch operation 3/10 success: τι επιστρέφεται;
- Rollback ή partial commit;
- User notification για partial success;

### 7.4 Resource Exhaustion
- Disk full: behavior;
- DB connection pool exhausted: behavior;
- Memory limit: behavior;
- Alerts για αυτά τα σενάρια;

### 7.5 Εξωτερικές Εξαρτήσεις
- Payment gateway down: fallback;
- Email service down: queue ή drop;
- CDN down: origin fallback;

**Output:**
| Σενάριο | Trigger | Detection | Behavior | Worst-Case Impact | Mitigation | Severity | Confidence |
|---------|---------|-----------|----------|-----------------|-----------|---------|------------|

---

## ΜΕΡΟΣ 8: CONCURRENCY & DISTRIBUTED STATE *(new)*

**Depth Budget: 4 ευρήματα max**

### 8.1 Distributed Locks
- Κρίσιμες operations: mutual exclusion mechanism;
- Lock expiry handling (process dies while holding lock);
- Deadlock detection;

### 8.2 Optimistic vs Pessimistic Concurrency
- Read-modify-write patterns: conflict detection;
- Lost update problem;
- Appropriate strategy ανά use case;

### 8.3 Split-Brain Scenarios
- Σε distributed deployment: partition tolerance;
- Consistency vs Availability trade-off: δηλωμένο;

### 8.4 Configuration Drift
- dev/staging/production: ίδιες ρυθμίσεις;
- Config changes: tracked σε version control;
- Infrastructure as Code ή manual;

**Output:**
| Εύρημα | Τοποθεσία | Σενάριο Αστοχίας | Severity | Confidence |
|--------|-----------|-----------------|---------|------------|

---

## ΜΕΡΟΣ 9: ΕΞΑΡΤΗΣΕΙΣ ΚΑΙ ΕΦΟΔΙΑΣΤΙΚΗ ΑΛΥΣΙΔΑ

**Depth Budget: 4 ευρήματα max**

### 9.1 Dependency Health
- Direct + transitive count;
- Γνωστά CVEs;
- Major version behind;
- Unmaintained (>1 year no commits);

### 9.2 Left-Pad Risk
- Registry disappearance: build breaks;
- Mirror/cache των dependencies;
- Personal repos / forks ως dependencies;

### 9.3 Vendor Lock-in
- Code change cost για αλλαγή provider;
- Proprietary vs open-source alternatives;
- Abstraction layer πάνω από cloud-specific services;

### 9.4 License Compatibility
- Όλες οι άδειες συμβατές;
- Copyleft (GPL) σε proprietary project;
- "No license" dependencies;

**Output:**
| Dependency | Version | License | CVE | Maintenance | Blast Radius | Severity | Confidence |
|-----------|---------|---------|-----|------------|-------------|---------|------------|

---

## ΜΕΡΟΣ 10: ΑΠΟΔΟΣΗ ΠΟΥ ΔΕΝ ΦΑΙΝΕΤΑΙ ΣΤΟ PROFILER

**Depth Budget: 4 ευρήματα max**

### 10.1 Connection Management
- Connections ανά request: κλείνουν σωστά;
- Connection pooling config;
- Pool exhaustion behavior;

### 10.2 Serialization Overhead
- Large payload serialize/deserialize cost;
- Oversized responses;
- Pagination: υπάρχει, συνεπές;

### 10.3 Logging Overhead
- Synchronous logs που μπλοκάρουν request;
- Debug logs σε production;

### 10.4 Orphaned Resources
- File handles / sockets που δεν κλείνουν;
- Memory leaks (static collections unbounded growth);
- Threads / goroutines που δεν τερματίζονται;

**Output:**
| Πρόβλημα | Τοποθεσία | Μηχανισμός | Επίπτωση | Severity | Confidence |
|---------|-----------|-----------|----------|---------|------------|

---

## ΤΕΛΙΚΗ ΑΝΑΦΟΡΑ

### Executive Summary
- Top 5 κρίσιμα ευρήματα (P0/P1) με **blast radius** ανά εύρημα
- Single Point of Failure
- Πρώτο 3AM alert prediction
- Μία αλλαγή → μέγιστη αξιοπιστία

### Severity Summary
*(Συμπληρώνεται ΑΥΤΟΜΑΤΑ από τα findings — μην βάζεις κάτι εδώ που δεν εμφανίζεται σε section)*

| Μέρος | P0 | P1 | P2 | P3 | Confidence Avg |
|-------|----|----|----|-----|---------------|
| 1. Χρονική Συμβατότητα | | | | | |
| 2. Σχεδιαστικές Αποφάσεις | | | | | |
| 3. Παρατηρησιμότητα & Κόστος | | | | | |
| 4. Ανθρώπινοι Παράγοντες | | | | | |
| 5. Ασφάλεια | | | | | |
| 6. Διαχείριση Δεδομένων | | | | | |
| 7. Αντιμετώπιση Αστοχίας | | | | | |
| 8. Concurrency & State | | | | | |
| 9. Εξαρτήσεις | | | | | |
| 10. Απόδοση | | | | | |
| **ΣΥΝΟΛΟ** | | | | | |

### Ship Decision
- **READY:** 0 P0, τα P1 έχουν owners και timelines
- **CONDITIONAL:** P1 υπάρχουν με ενεργά mitigations
- **NOT READY:** ≥1 P0

### Prioritized Action List
| Priority | Action | Owner | ETA | Blocks Deployment | Blast Radius |
|----------|--------|-------|-----|-------------------|-------------|

### Uncertainty Register
1. Top 3 claims most likely to be wrong (+ γιατί):
2. Requires runtime validation (static analysis insufficient):
3. Requires additional context to assess:
4. [ΕΙΚΑΣΙΑ] items που χρειάζονται επιβεβαίωση:

---

## JSON SUMMARY

```json
{
  "audit_type": "beyond-the-obvious-v7",
  "system_name": "...",
  "audit_date": "...",
  "scope": "all | [1,5,7]",
  "audience": "CTO | Tech Lead | Security Officer | New Developer",
  "input_available": ["source_code", "docs", "..."],
  "total_findings": {
    "P0": 0, "P1": 0, "P2": 0, "P3": 0
  },
  "by_category": {
    "temporal": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "HIGH|MEDIUM|LOW"},
    "design_decisions": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "observability_cost": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "human_factors": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "security": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "data_management": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "failure_handling": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "concurrency_state": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "dependencies": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."},
    "performance": {"P0": 0, "P1": 0, "P2": 0, "P3": 0, "confidence_avg": "..."}
  },
  "ship_decision": "READY | CONDITIONAL | NOT READY",
  "blocking_items": ["..."],
  "top_risk": "...",
  "single_point_of_failure": "...",
  "blast_radius_map": {"component_X": ["component_Y", "component_Z"]},
  "first_3am_alert_prediction": "...",
  "uncertainty_register": {
    "likely_wrong": ["claim_1", "claim_2", "claim_3"],
    "requires_runtime_validation": ["..."],
    "guesses_needing_confirmation": ["..."]
  }
}


COVERAGE MAP V7
Κατηγορία
Τι Ελέγχει
V6
V7
Χρονική Συμβατότητα
Timezones, DST, λήξεις, timeouts
✓
✓
Σχεδιαστικές Αποφάσεις
Idempotency, delivery, degradation, backpressure
✓
✓
Παρατηρησιμότητα
Metrics/Logs/Traces/Alerting/Cost (5 pillars)
partial
✓
Ανθρώπινοι Παράγοντες
Error messages, docs, bus factor, onboarding
✓
✓
Ασφάλεια
Mass assignment, IDOR, TOCTOU, side-channels, secrets
✓
✓
Διαχείριση Δεδομένων
Soft/hard delete, retention, cascade, migrations
✓
✓
Αντιμετώπιση Αστοχίας
Retries, poison msgs, partial success, exhaustion
✓
✓
Concurrency & State
Distributed locks, optimistic/pessimistic, config drift
✗
✓ NEW
Εξαρτήσεις
CVEs, left-pad, vendor lock-in, licenses
✓
✓ + blast radius
Απόδοση
Connections, serialization, logging, orphans
✓
✓
Input Declaration
Τι evidence έχω πριν ξεκινήσω
✗
✓ NEW
Audience Targeting
Ποιος διαβάζει → depth calibration
✗
✓ NEW
Scoping
Partial audit capability
✗
✓ NEW
Severity Calibration Rubric
Concrete criteria για P0-P3
✗
✓ NEW
Confidence Scoring
HIGH/MEDIUM/LOW per finding
✗
✓ NEW
Blast Radius Map
Failure propagation topology
✗
✓ NEW
Meta-Audit Placement
PRE-analysis, not post
wrong order
✓ FIXED
Depth Budgets
Max findings per section
✗
✓ NEW
JSON↔Table linkage
Aggregation rule
✗
✓ NEW
