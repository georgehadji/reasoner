---
name: reasoner-preset-manager
description: Manages the creation, validation, and maintenance of PipelinePreset configurations in the Reasoner project.
---

# Reasoner Preset Manager

This skill assists in the creation and management of `PipelinePreset` configurations within the Reasoner project.

## Workflow:

This skill provides guidance for managing `PipelinePreset` configurations, which are defined in `src/reasoner/domain/preset_registry.py`.

### 1. Creating a New Preset

To create a new preset, follow these steps:

-   **Define a Unique ID**: Choose a unique `id` for your preset (e.g., `my-new-method-budget`).
-   **Name and Description**: Provide a clear `name` and `description` that explains the preset's purpose and characteristics.
-   **Primary Model**: Specify the `primary_id`, which is the default model used when a phase-specific override is not present.
-   **Routing**: Define the `routing` dictionary to map specific pipeline phases to preferred LLM models. Refer to `src/reasoner/infrastructure/llm/registry.py` for a list of whitelisted models in `_MODEL_WHITELIST`.
-   **Fallback Routing**: Define the `fallback_routing` dictionary with alternative models for each phase, which will be used if the primary model fails or is unavailable.
-   **Notes**: Include `notes` to provide additional context, such as cost considerations, unique features, or performance characteristics.
-   **Environment Variables**: List any `required_env_vars` (e.g., `OPENROUTER_API_KEY`, `DEEPL_API_KEY`).

**Example Structure (from `src/reasoner/domain/preset_registry.py`):**

```python
    {
        "id": "multi-perspective-example",
        "name": "Multi-Perspective (Example)",
        "description": "An example preset showing how to configure models for different phases.",
        "primary_id": "gemini-pro",
        "routing": {
            "prompt_enhancement": "gemini-flash-lite",
            "classification": "gemini-flash-lite",
            "decomposition": "gemini-pro",
            "synthesis": "gemini-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "gemma-4-26b",
            "classification": "gemma-4-26b",
            "decomposition": "claude-sonnet",
            "synthesis": "glm-5.1"
        },
        "notes": [
            "Gemini Flash Lite for efficient early-phase processing.",
            "Gemini Pro for high-quality, complex reasoning and synthesis."
        ],
        "required_env_vars": ["OPENROUTER_API_KEY"],
    },
```

### 2. Modifying an Existing Preset

To modify an existing preset, locate its configuration dictionary in `_PRESET_CONFIGS` within `src/reasoner/domain/preset_registry.py` and update the relevant fields (e.g., `routing`, `fallback_routing`, `description`).

### 3. Validating Presets

Ensure that:

-   All model IDs specified in `routing` and `fallback_routing` exist in `_MODEL_WHITELIST` (see `src/reasoner/infrastructure/llm/registry.py`).
-   The `id` field is unique across all presets.
-   The preset structure adheres to the `PipelinePreset` dataclass definition in `src/reasoner/domain/preset_core.py`.
-   Run `python -m pytest test_presets.py` (if available) or relevant tests to validate changes.

## Resources:

-   `src/reasoner/domain/preset_registry.py`: Where all preset configurations are defined.
-   `src/reasoner/infrastructure/llm/registry.py`: Contains the `_MODEL_WHITELIST` for available LLMs.
-   `src/reasoner/domain/preset_core.py`: Defines the `PipelinePreset` dataclass structure.
-   `src/reasoner/core/constants.py`: Contains global constants, including default presets.
