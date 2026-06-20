# Reasoner Self-Analysis Plan

## Goal

Run the Reasoner pipeline live (real API calls) using the **multi-perspective-budget** preset,
feeding a detailed description of the codebase's current state as the problem statement.
Parse the synthesis output and implement the highest-priority bugs and fixes surfaced.

## Problem Statement (written to tasks/reasoner-self-analysis-prompt.txt)

Dense, factual description of the codebase including:
- Architecture: Hexagonal DDD + CQRS + Event Sourcing + Mixin Composition
- Known layer violations (3 documented in CLAUDE.md)
- Bugs already fixed this session (B-01 through B-08) — excluded from scope
- Question: what additional production-critical bugs, race conditions, security vulnerabilities,
  and architectural violations exist that have NOT been addressed?

## Execution

```bash
python main.py \
  --problem-file tasks/reasoner-self-analysis-prompt.txt \
  --preset multi-perspective-budget \
  --output tasks/reasoner-self-analysis-result.json \
  --top-k 2
```

Expected runtime: 3–8 minutes (budget tier, parallel perspectives).

## Output Parsing

Read `tasks/reasoner-self-analysis-result.json` → `final_solution` field.
Implement CRITICAL + HIGH severity items only. Note MEDIUM/LOW in lessons.md.

## Verification

After each fix:
```bash
python -m pytest tests/ -v -m "not slow and not integration and not searxng" --tb=short -q
```
