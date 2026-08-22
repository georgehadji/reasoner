---
name: map-subagents
description: Folder map of src/reasoner/subagents — intra-phase PhaseSubAgents grouped by phase (enhancement, decomposition, critique, search, synthesis), each with a HyperAgent that fans out in parallel. Use when adding or tuning a phase sub-agent.
folders:
  - src/reasoner/subagents
---

# src/reasoner/subagents — Folder Map

**Purpose:** Focused reasoning agents that run *inside* a pipeline phase. Same one-job-per-agent discipline as HyperGate, but these receive the mutable `PipelineState` (HyperGate's inputs are frozen) and return structured output. Each phase group has a `hyper_agent.py` that runs its members in parallel and synthesizes their results.

## Base

| File | What it does |
|------|--------------|
| `__init__.py` | Package doc + exports. |
| `base.py` | `PhaseSubAgent` — abstract base: one responsibility, state access, structured output, fail-safe. |
| `models.py` | `PhaseSubAgentInput`, `PhaseSubAgentOutput` — the communication protocol. |

## enhancement/ (prompt analysis, pre-Phase 0)

| File | What it does |
|------|--------------|
| `hyper_agent.py` | `EnhancementHyperAgent` — runs the three below in parallel, merges into an enhanced problem statement. |
| `ambiguity_detector.py` | What is unclear or vague in the problem statement. |
| `context_enricher.py` | What context is missing. |
| `scope_narrower.py` | Is the problem too broad, and how to narrow it. |

## decomposition/ (Phase 1)

| File | What it does |
|------|--------------|
| `hyper_agent.py` | `DecompositionHyperAgent` — three parallel sub-agents into one decomposition. |
| `structural_decomposer.py` | Hierarchical what/why/how breakdown. |
| `stakeholder_mapper.py` | Relevant perspectives and stakeholders. |
| `coverage_validator.py` | Do the sub-problems cover the original problem completely. |

## critique/ (Phase 3)

| File | What it does |
|------|--------------|
| `hyper_agent.py` | `CritiqueHyperAgent` — four parallel critique dimensions, synthesizes 0-10 scores. |
| `logic_critique.py` | Formal fallacies and structural flaws. |
| `evidence_critique.py` | Source/evidence quality and reliability. |
| `bias_critique.py` | Cognitive biases and framing effects. |
| `counterfactual.py` | "What if the opposite were true?" per candidate. |

## search/ (research methods)

| File | What it does |
|------|--------------|
| `hyper_agent.py` | `SearchHyperAgent` — three parallel search sub-agents. |
| `query_generator.py` | Diverse web-search queries. |
| `source_evaluator.py` | Credibility and relevance of results. |
| `gap_identifier.py` | Evidence still missing after a search round. |

## synthesis/ (Phase 5/6)

| File | What it does |
|------|--------------|
| `hyper_agent.py` | `SynthesisHyperAgent` — three parallel analysts, then the writer. |
| `consensus_mapper.py` | Points all perspectives agree on. |
| `contradiction_resolver.py` | Where perspectives disagree and why. |
| `evidence_weighter.py` | Which candidate arguments carry the strongest evidence. |
| `synthesis_writer.py` | Writes the final answer from the three analyses plus original state. |

## Key entry points & gotchas

- Pattern to copy when adding one: `X_SYSTEM` constant + `XSubAgent(PhaseSubAgent)` class + registration in the group's `hyper_agent.py` parallel fan-out.
- Sub-agents must fail safe — a failure degrades the phase, never raises into the request path.
- These take mutable `PipelineState`; HyperGate sub-agents (`src/reasoner/hypergate/`) take frozen inputs. Don't copy patterns across that line without checking.
- Which sub-agents run for a phase is resolved in `api/streaming.py` (`_get_phase_subagents`) and the preset config.
