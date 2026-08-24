# Context: Domain

## Directory: `src/reasoner/domain`

## Description
Domain logic models, entities, value objects, and business validation rules.

## Files
- **`__init__.py`**: Python package initialization module.
- **`api_keys.py`**: : Namespace that distinguishes Reasoner keys from OAuth JWTs on the wire.
- **`article_domain.py`**: ═════════════════════════════════════════════════════════════════════
- **`core_types.py`**: Domain core dataclasses extracted from models.py.
- **`credits.py`**: 1 credit = $0.001 USD of model spend. A budget run (~$0.02) costs ~20 credits,
- **`harness_metrics.py`**: Code or resource asset facilitating system functionality.
- **`model_capabilities.py`**: Domain value objects for model capability profiles (ACR Phase 2).
- **`models.py`**: Reasoner Domain Models - Pure Business Entities
- **`openrouter_models.json`**: Code or resource asset facilitating system functionality.
- **`pipeline_state.py`**: Spend ceilings resolved from the caller's subscription tier, carried on
- **`preset_core.py`**: Removed ProviderRouter and _REGISTRY imports to restore domain purity.
- **`preset_registry.py`**: ======================================================================================
- **`pricing.py`**: LLM Pricing Database
- **`saas.py`**: SaaS Domain Entities
- **`scoring_weights.py`**: Domain value objects for utility scoring weights (ACR Phase 3).
- **`spend_limits.py`**: Per-subscription-tier LLM spend ceilings.
- **`task_requirements.py`**: Domain value objects for task requirements (ACR Phase 3).
- **`telemetry.py`**: Domain value objects for per-call LLM telemetry (ACR Phase 1).

## Subfolders
- **`watermark`**: Watermarking entities and core validation rules for labeling generated content.
