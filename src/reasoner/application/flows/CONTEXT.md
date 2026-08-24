# Context: Flows

## Directory: `src/reasoner/application/flows`

## Description
High-level visual or logic pipelines coordinating distinct agent interactions.

## Files
- **`__init__.py`**: Application flows module.
- **`article.py`**: Feature flag: set ARTICLE_USE_ADAPTERS=1 to use the 11-phase adapter pipeline
- **`article_adapters.py`**: ═════════════════════════════════════════════════════════════════════
- **`article_phases.py`**: Pattern 1: Markdown links — [Source Title](https://url...)
- **`augmentation.py`**: ── Augmentation result cache (L1: in-memory LRU) ─────────────────────
- **`base.py`**: Base interfaces for workflow strategies.
- **`brainstorming.py`**: Brainstorming reasoning workflow strategy.
- **`brainstorming_phases.py`**: Code or resource asset facilitating system functionality.
- **`coding.py`**: Coding reasoning workflow strategy.
- **`coding_phases.py`**: Extract technology keywords from the problem
- **`cognitive.py`**: Code or resource asset facilitating system functionality.
- **`cognitive_phases.py`**: --- CoVE (Chain-of-Verification) ---
- **`debate.py`**: Debate reasoning workflow strategy.
- **`debate_phases.py`**: Extract stances from decomposition if available to create a meaningful debate
- **`delphi.py`**: Delphi method reasoning workflow strategy.
- **`delphi_phases.py`**: Extract numeric values
- **`dialectical.py`**: Dialectical, Scientific, Socratic, Pre-Mortem, Bayesian, and Analogical reasoning workflow strategies.
- **`dialectical_phases.py`**: Dialectical, Scientific, Socratic, Pre-Mortem, Bayesian, and Analogical phase logic.
- **`egress_rewrite_phase.py`**: Layer B: optional best-effort statistical-rewrite pass on the synthesis output.
- **`factory.py`**: Factory for creating workflow strategies.
- **`iterative_critique.py`**: Iterative Critique (LLM Debate) — Adversarial Refinement Strategy.
- **`iterative_critique_phases.py`**: Code or resource asset facilitating system functionality.
- **`jury.py`**: Jury reasoning workflow strategy.
- **`jury_phases.py`**: Ensure data is a dict
- **`language_probe_phase.py`**: Cross-lingual probe phase (Part B) — language-bias mitigation.
- **`multi_perspective.py`**: Multi-perspective reasoning workflow strategy.
- **`perspective_phases.py`**: Perspective and critique phases logic.
- **`pipeline_flow.py`**: Phase sequence registry and dispatcher for reasoning methods.
- **`prism_research.py`**: Code or resource asset facilitating system functionality.
- **`research.py`**: Research reasoning workflow strategy.
- **`research_phases.py`**: Research phase logic.
- **`runner.py`**: P1.9: Skip phase if spend cap was exceeded in a previous phase
- **`search_phases.py`**: Code or resource asset facilitating system functionality.
- **`services.py`**: Concrete implementation of workflow services.
- **`synthesis_phase.py`**: Simplified synthesis logic extracted from pipeline.py
- **`writing.py`**: Writing reasoning workflow strategy.
- **`writing_phases.py`**: Sonar native path: parse inline citations

## Subfolders
*No subfolders in this directory.*
