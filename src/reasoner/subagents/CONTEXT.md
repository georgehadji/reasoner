# Context: Subagents

## Directory: `src/reasoner/subagents`

## Description
Task-focused LLM subagents used in specific stages of the reasoning process.

## Files
- **`__init__.py`**: PhaseSubAgent package — intra-phase focused reasoning agents.
- **`base.py`**: ── Abstract interface ────────────────────────────────────────────
- **`models.py`**: Data models for PhaseSubAgent communication protocol.

## Subfolders
- **`enhancement`**: Deploys LLMs to enrich queries or refine search results before generations.
- **`synthesis`**: Deploys LLMs to synthesize competing viewpoints and produce a single master answer.
