# Tracked git hooks

These hooks are version-controlled (unlike the old `.git/hooks/*` scripts,
which never survived a `git clone`). Activate them once per clone:

```bash
git config core.hooksPath .githooks
```

| Hook | Runs | Mirrors |
|---|---|---|
| `pre-commit` | `scripts/scan-secrets.py` | was `.git/hooks/pre-commit` |
| `pre-push` | `scripts/ci-local.sh` (full suite) | `.github/workflows/{test,pr-architecture}.yml` |

Bypass a single run with `--no-verify` on the `git commit`/`git push` command.

See `docs/plans/architecture-score-9-remediation-plan.md`, Phase 0.2, and its
"Switching triggers" section — while the repo stays private on the free plan,
these hooks (not GitHub-hosted checks) are the real enforcement contract, not
a stopgap.
