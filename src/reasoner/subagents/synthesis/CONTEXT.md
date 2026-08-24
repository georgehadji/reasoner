# Context: Synthesis

## Directory: `src/reasoner/subagents/synthesis`

## Description
Deploys LLMs to synthesize competing viewpoints and produce a single master answer.

## Files
- **`__init__.py`**: Synthesis subagents — parallel analysis + writer for Phase 5/6.
- **`consensus_mapper.py`**: ConsensusMapperSubAgent — ONE JOB: identify which points all perspectives agree on.
- **`contradiction_resolver.py`**: ContradictionResolverSubAgent — ONE JOB: find disagreements between perspectives and explain why.
- **`evidence_weighter.py`**: EvidenceWeighterSubAgent — ONE JOB: score which candidate arguments have the strongest evidence.
- **`hyper_agent.py`**: SynthesisHyperAgent — orchestrates 3 parallel analysis subagents + 1 writer.
- **`synthesis_writer.py`**: The writer receives pre-built context from the hyper-agent

## Subfolders
*No subfolders in this directory.*
