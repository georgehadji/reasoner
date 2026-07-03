# Reasoner - Instructional Context

This document provides foundational context for AI agents working on the **Reasoner** project.

## Project Overview
Reasoner is a sophisticated, multi-method AI reasoning system designed for complex questions, strategic decisions, and research tasks. It follows a structured, multi-phase pipeline rather than one-shot completions.

### Core Architecture
- **Pipeline-Based:** Always works phase-by-phase:
    1.  **Classification:** Identifies task type and language.
    2.  **Decomposition:** Breaks the problem into sub-problems and assumptions.
    3.  **Context Vetting (Universal):** Iterative RAG with LLM deciding if more searches needed.
    4.  **Deep read_file (Optional):** Fetches full content from critical sources.
    5.  **Generation/Perspective Analysis:** Produces competing answers or perspectives.
    6.  **Critique/Scoring:** Evaluates candidates against various dimensions.
    7.  **Stress Testing/Verification:** Tests survivors for resilience and factual accuracy.
    8.  **Synthesis:** Produces a final, evidence-grounded answer with meta-audit insights.
- **Multi-Method Support:** `Multi-Perspective`, `Iterative`, `Debate`, `Jury`, `Research`, `Scientific`, `Socratic`.
- **Multi-Provider Routing:** Routes phases to different LLM providers (Anthropic, OpenAI, Google, Perplexity, Mistral, xAI, DeepSeek, Qwen, Kimi, GLM, MiniMax).
- **Iterative RAG:** Universal context vetting phase with iterative loop (max 3 iterations).
- **Specialized Source Types:** Filter searches by general, academic, social, news, code.
- **External Context API:** API endpoint for microservices architecture.
- **Interfaces:** CLI (`main.py`), FastAPI/SSE backend (`api.py`), and Next.js frontend (`ui-next/`).

## Technical Stack
- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pydantic (via `models.py`), Asyncio.
- **Frontend:** Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 (in `ui-next/`).
- **LLM Integration:** Native SDKs (Anthropic, Google, Mistral) and OpenAI-compatible endpoints for others.
- **Data Persistence:** Server-side response cache in `cache/`, client-side history in IndexedDB.

## Building and Running

### Installation
```bash
pip install -r requirements.txt
```
*Note: A `.env` file with relevant API keys is required for execution.*

### Running the Backend
To run the primary FastAPI application (defined in `asgi.py`):
```bash
uvicorn asgi:app --reload --port 8000
```
Then access `http://localhost:8003` (default port, configurable via `SERVER_PORT`).

To run the API entry point (defined in `api.py`):
```bash
uvicorn src.reasoner.api:app --reload --port 8000
```
Note: Ensure only one Uvicorn instance is running on the same port at a time.

### Running the CLI
```bash
# Basic run
python main.py --problem "Your question" --preset research-budget

# List available presets and models
python main.py --list-presets
python main.py --list-models

# Run with specialized source type
python main.py --problem "Your question" --source-type academic

# Save and resume state
python main.py --problem "..." --save-state state.json
python main.py --resume state.json
```

### Testing
```bash
# Run all tests
python -m pytest -v

# Run specific test suites
python -m pytest test_parsing.py test_models.py test_perplexity_config.py -q
```

## Development Conventions

### Coding Style
- **Python:** 4-space indentation. `snake_case` for functions, variables, and modules. `PascalCase` for classes, Enums, and Dataclasses.
- **Type Hints:** Required for public APIs and complex logic.
- **UI:** Confine all UI changes to `ui-next/`. Use React, TypeScript, and Tailwind CSS patterns.

### Project Organization
- `main.py` / `api.py`: Entry points.
- `pipeline.py`: Orchestrates the reasoning phases.
- `phases.py`: Contains prompts and phase-specific logic.
- `llm.py`: Provider abstraction and model registry.
- `presets.py`: Defines model routing and preset configurations.
- `models.py`: Data models and pipeline state.
- `parsing.py`: JSON extraction and repair logic.
- `renderer.py`: Terminal/CLI output rendering.

### Testing Guidelines
- Use `pytest`. Name test files `test_<area>.py`.
- Wrap related test cases in `Test...` classes.
- Always add regression tests when fixing parsing or routing issues.

### Commit Guidelines
- Use Conventional Commits (e.g., `feat:`, `fix:`, `docs:`, `ui:`).
- Describe UI changes clearly.
- Note if new API keys or `.env` changes are required.

## External Tools, Linters, and Formatters
To maintain code quality and consistency:
- **Ruff:** This project likely uses Ruff for linting and formatting (indicated by `.ruff_cache`). To run: `ruff check .` or `ruff format .`
- Always check `pyproject.toml`, `setup.cfg`, `.eslintrc.js`, etc., for specific configurations and other tools in use.

## Operational Realities
- **Routing & Fallbacks:** The system has a robust `ProviderRouter` in `llm.py` that handles provider-specific nuances and implements fallback logic if a primary model fails.
- **Structured Output:** The system heavily relies on JSON extraction (see `parsing.py`). Some models (like Perplexity) use specific `response_format` configurations.
- **Rate Limits:** Use `--sequential` in the CLI or the "Sequential" toggle in the UI for methods involving many parallel calls to rate-limited providers.
- **Dependencies (Optional):** Redis is optional for local development but recommended for high-load production environments to enable cross-worker state management and advanced caching.


## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `../tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management
1. **Plan First**: Write plan to `../tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `../tasks/todo.md`
6. **Capture Lessons**: Update `../tasks/lessons.md` after corrections

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **Root Causes**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
