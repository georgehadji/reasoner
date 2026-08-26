---
name: map-ops
description: Folder map of scripts/, .githooks/, .github/workflows/, migrations/, sdk/, benchmarks/, nginx/, audit/, plans/, repo-level skills/, plus root entry points, config files, and which directories are runtime junk. Use for CI gates, ratchets, DB migrations, the TypeScript SDK, or orienting outside src/ and ui-next/.
folders:
  - scripts
  - .githooks
  - .github
  - migrations
  - sdk
  - benchmarks
  - nginx
---

# Ops, tooling, and repo root — Folder Map

**Purpose:** Everything outside the application code: CI gates and ratchets, git hooks, database migrations, the published TypeScript SDK, benchmarks, deployment configs, and the repo's root entry points.

## scripts/ — CI gates, ratchets, maintenance

| File | What it does |
|------|--------------|
| `ci-local.sh` | Local mirror of the GitHub Actions gates. Run before pushing. |
| `check_no_registry_bypass.py` | CI guard: `application/`, `domain/`, `core/` must not import `infrastructure.llm.registry` directly. |
| `count_importlinter_exceptions.py` | Semantic counter for `.importlinter` `ignore_imports` — the exception ratchet. |
| `fix_importlinter.py` | Helper for updating that exception list. |
| `ruff_ratchet.py` | Ratchet for `ruff check src/` violation count. |
| `mypy_ratchet.py` | Ratchet for `mypy src/reasoner` violation count. |
| `package_coverage_gate.py` | Per-package coverage floor read from `coverage.xml`. |
| `check_skill_maps.py` | Compares the folders each `.claude/skills/map-*` skill declares against `.map-manifest.json` and reports which map a new or deleted file made stale. `--update` re-baselines. Wired into `.githooks/pre-commit` as a warning. |
| `scan-secrets.py` | Secret scanner for API keys and tokens in source. |
| `lock_requirements.sh` | Hash-locked Python dependency lockfile. |
| `pin_base_images.sh` | Pins Docker base images by digest. |
| `update_mindmap_meta.py` | Post-commit: patches live counts into `ARCHITECTURE_MINDMAP.md` and regenerates `ui-next/src/lib/capabilities.generated.ts`. |
| `update_openrouter_catalogue.py` | Refreshes the bundled OpenRouter model catalogue. |
| `validate_presets.py` | Validates every preset in the registry. |
| `generate_preset_docs.py` | Regenerates `docs/methods_and_presets.md` and `docs/preset-phase-model-matrix.md` from `domain/preset_registry.py`. Both are pure projections of the registry; nothing produced them before, so they rotted. `--check` exits 1 when stale, for CI. |
| `capture_article_baseline.py` | Captures and updates the Article pipeline golden baseline. |
| `migrate_events_sqlite_to_pg.py` | SQLite to PostgreSQL event store migration. |
| `migrate_encryption_v2.py` | Re-encrypts events missing the v2 envelope or blind index. |
| `start_all.py` | Server launcher (mirrors `src/reasoner/start_all.py`). |
| `run_method_tests.py`, `run_3more_tests.py`, `run_batch4.py`, `jury_fix_test.py`, `verify_swaps.py` | Ad-hoc sequential method test runners. |
| `extract_e1.py`, `re_extract_e1.py`, `extract_run_stream.py`, `move_methods.py`, `cleanup_streaming.py` | One-off refactor helpers; historical. |

## .githooks/ and .github/workflows/

| File | What it does |
|------|--------------|
| `.githooks/pre-commit` | Tracked pre-commit hook — survives clone, unlike untracked `.git/hooks`. |
| `.githooks/pre-push` | Runs `scripts/ci-local.sh`. |
| `.githooks/README.md` | How to enable via `core.hooksPath`. |
| `workflows/test.yml` | Test suite. |
| `workflows/coverage.yml` | Coverage gate. |
| `workflows/pr-architecture.yml` | Import-linter, ratchets, registry-bypass guard. |
| `workflows/security.yml` | Secret scan and security checks. |
| `workflows/self-healing-ci.yml` | healing-profile, loop1-static, loop2-runtime, loop3-evolutionary, verification. Coverage 60% fail / 80% warn. |
| `workflows/release-sdk.yml` | Publishes the TypeScript SDK. |

## migrations/ — PostgreSQL schema

| File | What it adds |
|------|--------------|
| `001_saas_init.sql` | Base SaaS schema. |
| `002_auth_audit.sql` | Auth audit log. |
| `003_add_indexes.sql` | Indexes. |
| `004_failed_webhook_events.sql` | Billing dead-letter table. |
| `005_account_deletion_log.sql` | GDPR deletion log. |
| `006_call_telemetry.sql` | Per-call telemetry (ACR Phase 1). |
| `007_credits_and_api_keys.sql` | Credit ledger and user API keys. |
| `008_encryption_indexes.sql` | Blind-index columns. |
| `alembic/env.py`, `alembic/script.py.mako` | Alembic config and template (`alembic.ini` lives at repo root). |
| `alembic/versions/df9629e72f17_baseline.py` | Baseline of the whole schema. |
| `alembic/versions/20260501_*_add_paypal_and_rename_external_cols.py` | PayPal support, provider-specific column names. |
| `alembic/versions/20260502_*_add_oauth_columns.py` | `auth_provider` and `avatar_url` on users. |

## sdk/ — published TypeScript client

| Path | What it is |
|------|-----------|
| `contract/events.json`, `contract/tools.json`, `contract/openapi-digest.json` | The pinned contract the backend must keep satisfying (`tests/test_sdk_contract.py`, `tests/test_agent_tools_contract.py`). |
| `typescript/src/client.ts` | The public client surface. |
| `typescript/src/http.ts`, `typescript/src/sse.ts` | Transport; the SSE reader handles frames split across multi-byte characters. |
| `typescript/src/events.ts`, `types.ts`, `errors.ts`, `index.ts` | Event and type definitions, error classes, barrel export. |
| `typescript/test/*.test.ts` | client, contract, sse, errors tests. |
| `typescript/dist/` | Build output — generated, do not edit. |

## benchmarks/

`benchmark_vs_diversity.py` (VS versus direct generation), `benchmark_vs_calibration.py` (verbalized entropy versus uncertainty), `benchmark_vs_latency.py` (per deployment profile), `vs_latency_overhead.md` (results).

## Deployment and other folders

| Path | What it is |
|------|-----------|
| `nginx/nginx.conf` | Reverse-proxy config (see also `Caddyfile`, `Caddyfile.prod`). |
| `audit/01..06_*.md` | Six-part audit set: executive summary, findings register, implementation plan, implementation instructions, architecture review, testing gaps. |
| `plans/` | `PRODUCTION_READINESS_PLAN.md`, `architecture_risk_mitigation_plan.md`. |
| `skills/` | Repo-level skills separate from `.claude/skills/`: `llm-routing-optimizer`, `reasoner-preset-manager`, `reasoner-test-generator`. |
| `graphify/`, `graphify-out/` | Knowledge-graph tooling and its generated output, rebuilt by post-commit and post-checkout hooks. |
| `deepseek-harness/` | Standalone experiment harness. |

## Repo root — the files that matter

| File | What it does |
|------|--------------|
| `main.py` | CLI shim to `reasoner.main`. |
| `asgi.py` | ASGI app for uvicorn (`uvicorn asgi:app --port 8003`). |
| `start_all.py`, `start_all.bat`, `restart_servers.bat`, `kill_servers.py` | Start and stop backend plus frontend. |
| `mcp_server.py` | MCP server entry point. |
| `pyproject.toml`, `requirements.txt`, `requirements.lock` | Package metadata and dependencies; the lock is hash-pinned. |
| `pytest.ini` | Test paths, markers, parallel options, coverage config. |
| `.importlinter` | Layer contracts and the ignored-import exception list (ratcheted). |
| `.pre-commit-config.yaml` | Pre-commit hooks. |
| `alembic.ini` | Migration config. |
| `Dockerfile`, `docker-compose.yml`, `docker-compose.observability.yml`, `docker-entrypoint.sh`, `.dockerignore` | Container build and stack, including the `sandbox-worker` service. |
| `Caddyfile`, `Caddyfile.prod` | Edge and TLS. |
| `.env.example` | Every supported environment variable with sample values. |
| `CLAUDE.md`, `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`, `AUTHORS` | Project documentation. |
| `openrouter_models.json`, `openrouter_models_formatted.txt` | Bundled catalogue snapshot used by pricing and capability inference. |

**Also at root:** many historical audit reports, plans, transcripts, and scratch scripts (`*_report.md`, `check_*.py`, `find_*.py`, `temp_*.py`, root-level `test_*.py`, `pytest_full_output*.txt`, `todo.md` / `todo.txt`, `*.log`). Not load-bearing — do not treat them as current specs, and do not add more.

## Runtime and generated directories (never edit or commit)

`cache/`, `history/`, `uploads/`, `logs/`, `graphify-out/`, `src/reasoner/graphify-out/`, `.reports/`, `.benchmarks/`, `.hypothesis/`, `.ruff_cache/`, `.import_linter_cache/`, `.worktrees/`, `.tmp_manual_temp/`, `node_modules/`, `ui-next/.next/`, `sdk/typescript/dist/`, and the SQLite files `errors.db` and `feedback.db`.

## Key gotchas

- Run `scripts/ci-local.sh` before pushing; it is the same gate set CI runs.
- Ratchets only go down. If `ruff_ratchet.py` or `mypy_ratchet.py` fails, fix violations instead of raising the number; same for `.importlinter` exceptions.
- `ui-next/src/lib/capabilities.generated.ts` and the `ARCHITECTURE_MINDMAP.md` counters are written by `update_mindmap_meta.py` post-commit — edit the script, not its outputs.
- `sdk/contract/*.json` is a published contract with tests pinning it. Changing an event or tool shape means updating contract and SDK together.
- Two skill directories exist: `.claude/skills/` (agent-facing, including these maps) and `skills/` (repo-level). Check both before writing a new one.
