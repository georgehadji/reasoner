# Context: Critique

## Directory: `src/reasoner/subagents/critique`

## Description
Deploys LLMs to critique and score competing generated response options.

## Files
- **`__init__.py`**: Critique subagents — parallel critique dimensions for Phase 3.
- **`bias_critique.py`**: BiasCritiqueSubAgent — ONE JOB: detect cognitive biases and framing effects.
- **`counterfactual.py`**: CounterfactualSubAgent — ONE JOB: explore "what if the opposite were true?" for each candidate.
- **`evidence_critique.py`**: EvidenceCritiqueSubAgent — ONE JOB: evaluate quality and reliability of sources/evidence.
- **`hyper_agent.py`**: CritiqueHyperAgent — orchestrates 4 parallel critique subagents and synthesizes scores.
- **`logic_critique.py`**: LogicCritiqueSubAgent — ONE JOB: identify formal logical fallacies and structural flaws.

## Subfolders
*No subfolders in this directory.*
