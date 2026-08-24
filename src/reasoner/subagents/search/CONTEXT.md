# Context: Search

## Directory: `src/reasoner/subagents/search`

## Description
Deploys LLMs to dynamically formulate search queries during the context vetting phase.

## Files
- **`__init__.py`**: Search subagents — query generation and source evaluation.
- **`gap_identifier.py`**: GapIdentifierSubAgent — ONE JOB: identify what evidence is still missing after search.
- **`hyper_agent.py`**: SearchHyperAgent — orchestrates 3 parallel search subagents.
- **`query_generator.py`**: QueryGeneratorSubAgent — ONE JOB: generate diverse search queries for web research.
- **`source_evaluator.py`**: SourceEvaluatorSubAgent — ONE JOB: evaluate credibility and relevance of search results.

## Subfolders
*No subfolders in this directory.*
