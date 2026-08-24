# Context: Sub Agents

## Directory: `src/reasoner/hypergate/sub_agents`

## Description
Hypergate sub-agent controllers coordinating specialized reasoning tasks.

## Files
- **`__init__.py`**: On-demand only (image generation) — deliberately NOT in the Phase-1 gather.
- **`complexity_estimator.py`**: ComplexityEstimatorSubAgent — ONE JOB: estimate whether the problem is simple,
- **`direct_detector.py`**: DirectDetectorSubAgent — ONE JOB: decide whether the problem can be answered
- **`image_model_selector.py`**: ImageModelSelector — ONE JOB: map an image prompt to a capability family and a
- **`language_detector.py`**: LanguageDetectorSubAgent — ONE JOB: detect the language of the input text.
- **`method_classifier.py`**: Opaque taxonomy — letters only, no real method names visible to LLM.
- **`tie_breaker.py`**: TieBreakerSubAgent — ONE JOB: resolve routing ambiguity when Phase-1 sub-agents
- **`web_detector.py`**: WebSearchDetectorSubAgent — ONE JOB: decide whether the problem requires

## Subfolders
*No subfolders in this directory.*
