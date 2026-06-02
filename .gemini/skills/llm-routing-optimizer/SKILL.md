---
name: llm-routing-optimizer
description: Provides expertise and workflows for optimizing LLM routing across different reasoning phases based on cost, speed, quality, and specific model strengths.
---

# LLM Routing Optimizer

This skill helps in fine-tuning the `ProviderRouter` in `llm.py` and updating routing logic within presets to optimize overall pipeline performance and resource utilization.

## Workflow:

This skill provides expertise and workflows for optimizing LLM routing across different reasoning phases within the Reasoner project.

### 1. Understanding LLM Routing

LLM routing is primarily managed by the `ProviderRouter` in `src/reasoner/infrastructure/llm/llm.py` and defined within the `routing` and `fallback_routing` fields of `PipelinePreset` configurations in `src/reasoner/domain/preset_registry.py`.

### 2. Strategies for Optimization

Consider the following strategies when optimizing LLM routing:

-   **Cost-Effectiveness**: Use cheaper, faster models (e.g., `gemini-flash-lite`, `gemma-4-26b`) for simpler, early pipeline phases like `classification` or `prompt_enhancement`.
-   **Quality & Complexity**: Reserve high-quality, more expensive models (e.g., `gemini-pro`, `claude-sonnet`, `qwen3.6-plus`) for complex reasoning, generation, and synthesis phases (e.g., `decomposition`, `constructive`, `synthesis`).
-   **Speed**: Prioritize faster models for phases that require quick turnaround or have high throughput needs.
-   **Specific Model Strengths**: Leverage models known for particular strengths (e.g., `sonar-pro` for fact-checking/scoring, `kimi-k2-6` for agentic reasoning or code generation).
-   **Cross-Ecosystem Diversity**: Utilize models from different providers in fallback routes (`fallback_routing`) to ensure robustness and mitigate single-provider failures or biases.
-   **Dynamic Routing (Advanced)**: For more advanced scenarios, consider extending the `ProviderRouter` logic in `llm.py` to implement dynamic routing based on real-time factors like model latency, token usage, or even the complexity of the current problem.

### 3. Implementing Routing Changes

1.  **Identify Target Preset**: Determine which preset in `src/reasoner/domain/preset_registry.py` needs optimization.
2.  **Update Routing Configuration**: Modify the `routing` and `fallback_routing` dictionaries within the chosen preset's configuration.
3.  **Validate Models**: Ensure all new model IDs are present in the `_MODEL_WHITELIST` in `src/reasoner/infrastructure/llm/registry.py`.
4.  **Test**: Run relevant tests (`pytest`) to ensure the new routing logic functions as expected and does not introduce regressions.

## Resources:

-   `src/reasoner/infrastructure/llm/llm.py`: Contains the `ProviderRouter` implementation.
-   `src/reasoner/domain/preset_registry.py`: Defines all `PipelinePreset` configurations, including routing logic.
-   `src/reasoner/infrastructure/llm/registry.py`: Lists available LLMs in `_MODEL_WHITELIST`.
-   `src/reasoner/core/constants.py`: Contains global constants relevant to LLM usage and defaults.
