# Context: Translation

## Directory: `src/reasoner/infrastructure/translation`

## Description
Translation adapter wrappers utilized during the classification or synthesis phases to adapt response languages.

## Files
- **`__init__.py`**: Translation infrastructure.
- **`composite.py`**: CompositeTranslator: DeepL → LLM → identity fallback chain.
- **`deepl_client.py`**: DeepL API client for text translation.
- **`llm_translator.py`**: LLM-backed translation adapter — key-free fallback for the CompositeTranslator.

## Subfolders
*No subfolders in this directory.*
