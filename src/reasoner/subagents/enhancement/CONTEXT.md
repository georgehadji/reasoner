# Context: Enhancement

## Directory: `src/reasoner/subagents/enhancement`

## Description
Deploys LLMs to enrich queries or refine search results before generations.

## Files
- **`__init__.py`**: Enhancement subagents — prompt analysis and refinement.
- **`ambiguity_detector.py`**: AmbiguityDetectorSubAgent — ONE JOB: identify what is unclear or vague in the problem statement.
- **`context_enricher.py`**: ContextEnricherSubAgent — ONE JOB: identify what context is missing from the problem.
- **`hyper_agent.py`**: EnhancementHyperAgent — orchestrates 3 parallel enhancement subagents.
- **`scope_narrower.py`**: ScopeNarrowerSubAgent — ONE JOB: determine if the problem is too broad and suggest narrowing.

## Subfolders
*No subfolders in this directory.*
