# Contributing to Reasoner

Thanks for your interest in contributing! Reasoner is a multi-LLM reasoning orchestrator with a Python/FastAPI backend and a Next.js frontend. This guide will get you from zero to a merged PR.

For a higher-level overview of the architecture, conventions, and gotchas, see [`knowledge.md`](./knowledge.md).

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Prerequisites](#prerequisites)
3. [Project Setup](#project-setup)
4. [Development Workflow](#development-workflow)
5. [Testing](#testing)
6. [Code Style & Linting](#code-style--linting)
7. [Commit Guidelines](#commit-guidelines)
8. [Pull Request Guidelines](#pull-request-guidelines)
9. [Reporting Bugs & Requesting Features](#reporting-bugs--requesting-features)

---

## Code of Conduct

Be respectful, be constructive, assume good intent. Harassment of any kind is not tolerated. Disagreements are fine; disagreeable behavior is not.

---

## Prerequisites

- **Python 3.12+**
- **Node.js 20+** (required for the `ui-next/` frontend)
- **Git**
- An **OpenRouter API key** (recommended — one key, 350+ models) *or* individual provider keys (OpenAI, Anthropic, Google, DeepSeek, Mistral, xAI, Perplexity, Ollama)

---

## Project Setup

### 1. Fork & clone

```bash
git clone https://github.com/<your-username>/Reasoner.git
cd Reasoner
git remote add upstream https://github.com/tesse/Reasoner.git
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set at minimum:
#   OPENROUTER_API_KEY=sk-or-v1-...
```

### 3. Backend

```bash
python -m venv .venv

# Windows (cmd / bash)
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Frontend

```bash
cd ui-next
npm install
cd ..
```

### 5. Sanity check

```bash
python main.py --list-presets   # should print the preset table
python -m pytest tests/ -q -m "not slow and not integration"
```

---

## Development Workflow

### Branching

- Create feature branches off `main`:
  ```bash
  git checkout -b feat/<short-description>
  git checkout -b fix/<short-description>
  ```
- Keep branches focused — one logical change per PR.

### Run everything locally

```bash
python start_all.py
```

This launches:

| Service      | URL                       | Notes                                 |
|--------------|---------------------------|---------------------------------------|
| FastAPI API  | `http://localhost:8003`   | Configurable via `SERVER_PORT`        |
| Next.js UI   | `http://localhost:3000`   | From `ui-next/`                       |

### Run services individually

```bash
# Backend only
uvicorn asgi:app --reload --port 8003

# Frontend only
cd ui-next && npm run dev
```

Only one Uvicorn instance should bind a given port at a time.

### CLI usage while developing

```bash
python main.py --problem "Your test question" --preset debate-budget
python main.py --problem "..." --sequential          # for rate-limited providers
python main.py --problem-file problem.txt --output results.json
```

### Keeping your branch fresh

```bash
git fetch upstream
git rebase upstream/main
```

---

## Testing

### Running the suite

```bash
# Fast subset (recommended during iteration)
python -m pytest tests/ -v -m "not slow and not integration"

# Full suite (800+ tests)
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=src/reasoner --cov-report=html
```

Coverage reports land in `htmlcov/`. Config lives in [`pytest.ini`](./pytest.ini); `pythonpath = src` is set there so tests can import `reasoner.*` from the repo root. Tests run in parallel by default (`-n auto --dist loadscope`) and use `asyncio_mode = auto`.

### Writing tests

- Put tests under `tests/`, named `test_<area>.py`.
- Group related cases in `class Test...` containers.
- Mark slow or integration tests:
  ```python
  import pytest

  @pytest.mark.slow
  def test_large_pipeline(): ...

  @pytest.mark.integration
  def test_live_provider(): ...
  ```
- **Always add a regression test** when fixing a parsing or routing bug. Never trust that an LLM edge case is one-off.
- Prefer testing the public phase interfaces (`pipeline.py`, `phases/*.py`) over internal helpers.
- For JSON parsing work, exercise [`parsing.py`](./src/reasoner/parsing.py) with real-world malformed samples — don't mock them away.

### Manual verification

Before marking a task done:

- Run the relevant CLI invocation end-to-end (e.g. `python main.py --problem "..." --preset <your-method>`).
- Check that SSE streaming still emits phase events via the UI or `curl`.
- Confirm the final `state.final_solution.epistemic_label` is set (`VERIFIED` / `HYPOTHESIS` / `UNKNOWN`).

---

## Code Style & Linting

### Python

- **4-space indentation**, no tabs.
- `snake_case` for functions, variables, modules.
- `PascalCase` for classes, Enums, and dataclasses.
- **Type hints are required** on public APIs and any non-trivial function.
- Run Ruff before committing:
  ```bash
  ruff check src/reasoner/
  ruff format src/reasoner/
  ```

### TypeScript / Frontend

- All UI changes belong in `ui-next/`.
- Follow existing React + TypeScript + Tailwind patterns.
- Run the linter:
  ```bash
  cd ui-next && npm run lint
  ```

### Hard rules

- **Never silence type errors with `Any` / `any`** — fix the underlying type.
- **Never hand-roll `json.loads` on LLM output** — route it through [`src/reasoner/parsing.py`](./src/reasoner/parsing.py), which has repair logic for truncated / fenced responses.
- **Don't hardcode vendor model strings** (e.g. `anthropic/claude-3-opus-20240229`). Use model aliases defined in `llm.py` / `presets.py` (`claude-sonnet`, `gemini-pro`, `deepseek-v3.1-nex-n1`, etc.).
- **Fallbacks should be cross-lab.** Don't fall back to a different model from the same provider — the point is diversity. See the routing philosophy section of `knowledge.md`.
- **Epistemic labels are heuristic.** Don't treat `VERIFIED` as a factual guarantee in user-facing copy.

---

## Commit Guidelines

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <short summary>

<optional body explaining the why>

<optional footer: BREAKING CHANGE, issue refs>
```

Common types:

| Type       | Use for                                              |
|------------|------------------------------------------------------|
| `feat`     | New feature or user-visible capability               |
| `fix`      | Bug fix                                              |
| `docs`     | Docs-only changes                                    |
| `ui`       | Frontend-only changes in `ui-next/`                  |
| `refactor` | Code change that is neither a fix nor a feature      |
| `test`     | Adding / updating tests                              |
| `chore`    | Build, tooling, deps, CI                             |
| `perf`     | Performance improvement                              |

### Extra rules

- Keep the subject under ~72 characters.
- If your change requires new API keys or `.env` variables, **call that out in the body** — reviewers need to replicate the environment.
- If you touch presets or routing, note whether the change is cost-neutral or affects budget/premium tier pricing.

Example:

```
feat(presets): add analogical-premium preset with Gemini primary

Adds a Premium tier preset for analogical reasoning with Gemini as the
Phase-2 primary and Claude + Moonshot as cross-lab critics. Estimated
cost: ~$0.18/run.

Requires: GOOGLE_API_KEY or OPENROUTER_API_KEY.
```

---

## Pull Request Guidelines

### Before opening a PR

- [ ] Rebased on latest `upstream/main`
- [ ] All tests pass locally (`python -m pytest tests/ -v`)
- [ ] Ruff clean (`ruff check src/reasoner/`)
- [ ] Frontend lint clean if UI changed (`cd ui-next && npm run lint`)
- [ ] Added / updated tests for the change (regression test for bug fixes)
- [ ] Updated docs (`README.md`, `knowledge.md`, preset tables, etc.) if behavior or commands changed
- [ ] No new API keys silently required — any new env var is documented in `.env.example` and the PR description

### PR description template

Include:

1. **What** changed and **why**.
2. **How to test** — concrete commands or UI steps.
3. **Risk / blast radius** — what could break, which phases or presets touched.
4. **Screenshots / terminal output** for UI or CLI-visible changes.
5. **Related issues** — `Closes #123`.

### Review expectations

- Keep PRs small and focused. Split large refactors into reviewable chunks.
- Respond to review comments rather than force-pushing away discussion — squash at merge time.
- Don't merge your own PR without approval unless you're a maintainer handling a trivial docs fix.

---

## Reporting Bugs & Requesting Features

### Bugs

Open a GitHub issue with:

- **What happened** vs **what you expected**
- Exact CLI command or API request (redact keys)
- Python version (`python --version`) and OS
- Preset / routing config used
- Relevant snippets from `server_err.log`, `server_out.log`, or the pipeline state JSON
- Minimum reproduction if possible

### Feature requests

- Describe the **problem first**, then your proposed solution.
- Note whether it fits as a new **preset**, a new **reasoning method** (in `src/reasoner/phases/`), or infrastructure (router, cache, UI).
- Flag any cost implications or new provider dependencies.

---

## Questions?

Open a GitHub Discussion or tag a maintainer on an issue. Happy reasoning.
