# /test — Run Tests

Run the backend test suite with appropriate flags.

`pytest ... | tail -N` masks the real exit code: bash reports the last
command in a pipe (`tail`, which always exits 0), not pytest's. Every example
below sets `pipefail` first, so `$?` after the pipeline is still pytest's exit
code. See docs/plans/root-cause-remediation-2026-09-07.md P1 step 7.

**Quick (skip slow/integration):**
```bash
cd "E:/Documents/Vibe-Coding/Reasoner" && set -o pipefail && python -m pytest tests/ -v -m "not slow and not integration" --tb=short -q 2>&1 | tail -30
```

**All tests:**
```bash
set -o pipefail && python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

**Single file:**
```bash
python -m pytest tests/test_<name>.py -v
```

**With coverage:**
```bash
set -o pipefail && python -m pytest tests/ --cov=src/reasoner --cov-report=term-missing -q 2>&1 | tail -20
```

**Frontend type-check:**
```bash
cd ui-next && npx tsc --noEmit 2>&1 | head -30
```

Coverage gate: 60% = fail, 80% = warn (self-healing CI).
