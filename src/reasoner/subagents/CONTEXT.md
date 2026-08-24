# Context: Subagents

## Directory: `src/reasoner/subagents`

## Description
Task-focused LLM subagents used in specific stages of the reasoning process.

## Files
- **`__init__.py`**: PhaseSubAgent package — intra-phase focused reasoning agents.
- **`base.py`**: ── Abstract interface ────────────────────────────────────────────
- **`models.py`**: Data models for PhaseSubAgent communication protocol.

## Subfolders
- **`critique`**: Deploys LLMs to critique and score competing generated response options.
- **`decomposition`**: Deploys LLMs to deconstruct the problem and formulate research assumptions.
- **`enhancement`**: Deploys LLMs to enrich queries or refine search results before generations.
- **`search`**: Deploys LLMs to dynamically formulate search queries during the context vetting phase.
- **`synthesis`**: Deploys LLMs to synthesize competing viewpoints and produce a single master answer.
