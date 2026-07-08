# ADR-004: Cross-Lab LLM Routing

**Status:** Accepted · **Date:** 2026-07-08
**Context:** Implemented as part of pipeline v2.

## Context

LLM responses can suffer from echo chambers — the same training data biases across models from the same lab. Using multiple labs for different pipeline phases improves diversity of perspectives and reduces systematic errors.

## Decision

Implement a **cross-lab routing strategy**:

1. **Primary provider:** OpenRouter (single API key for 350+ models across 12+ labs)
2. **Fallback chain:** Anthropic direct → OpenAI direct → Google direct (for critical paths when OpenRouter is down)
3. **Diversity invariant:** Phase 2 (Perspectives) must use ≥3 different labs in Budget tier, ≥4 in Premium tier
4. **Scoring rule:** The scorer model must be from a different ecosystem than the dominant generator model
5. **Phase-specific routing:** Each phase role has a configured model; the `ProviderRouter` resolves roles to models

**Whitelist:** 28 directly registered models (`_MODEL_WHITELIST`) with explicit lab assignments. All other OpenRouter models are accessible but not explicitly routed.

## Consequences

**Positive:**
- Cross-lab diversity reduces echo-chamber effect
- Single OpenRouter key simplifies auth
- Explicit fallback chain provides resilience
- 28 whitelisted models are curated for quality

**Negative:**
- OpenRouter is a single point of failure (mitigated by direct fallback adapters)
- Cross-lab diversity increases cost (Premium tier uses more expensive models)
- Whitelist requires manual updating when new models are added
