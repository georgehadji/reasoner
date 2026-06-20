# Verbalized Sampling (VS) Architecture

## Overview

Verbalized Sampling is a reasoning primitive that replaces single-shot LLM generation with **k candidate generation + probability-weighted selection + NLI verification**. It is integrated into the ARA pipeline behind feature flags, allowing zero-downtime rollout and A/B testing.

## Integration Points

| Stage | File | Flag | Fallback when disabled |
|---|---|---|---|
| Probe Generation | `phases/vs_probe_generation.py` | `probe_generation` | Return original query |
| Decomposition | `phases/vs_decomposition.py` | `decomposition` | Return original query |
| Coverage Audit | `phases/vs_coverage_audit.py` | `coverage_audit` | `coverage_ratio=1.0` |
| Generation | `phases/vs_generation.py` | `generation` | Direct single LLM call |
| Calibration | `phases/vs_calibration.py` | `calibration` | Perfect default signals |
| Claim Extraction | `phases/vs_claim_extraction.py` | `claim_extraction` | Pass-through candidate texts |
| Verification Routing | `phases/vs_verification_routing.py` | `verification_routing` | `NLI_ONLY` |
| Conflict Surfacing | `phases/vs_conflict_surfacing.py` | `conflict_surfacing` | Empty list |
| Behavioral Audit | `phases/vs_behavioral_audit.py` | `behavioral_audit` | No-op |

## Configuration

### Feature Flags

```python
from reasoner.vs_config import VSFeatureFlags

# All enabled (default)
flags = VSFeatureFlags()

# All disabled — identical to pre-VS pipeline
flags = VSFeatureFlags.all_disabled()
```

### Deployment Profiles

| Profile | NLI Budget | Use Case |
|---|---|---|
| `LATENCY_SENSITIVE` | 1 | Real-time chat, low-latency APIs |
| `BALANCED` | 3 | Default for most pipelines |
| `MAX_ACCURACY` | 5 | Regulated verticals, safety-critical |

### Vertical Configs

| Vertical | k | Tail Threshold | Compliance Flags |
|---|---|---|---|
| Radiology | 7 | 0.10 | `fda_510k`, `hipaa_minimal` |
| Legal | 5 | 0.08 | `human_review_on_low_prob` |
| Aerospace | 5 | 0.06 | `cmmc_lvl2` |

## Generation Strategies

- **BEST_VERIFIABLE** (default): Run NLI on top candidates, select highest NLI score.
- **ENSEMBLE**: Select highest probability candidate.
- **TOP_PROBABILITY**: Select highest probability candidate.

## Fallback Behavior

The generation stage has a 3-level fallback:
1. **L1**: Retry with same prompt on `ProviderError`
2. **L2**: Retry with simplified prompt
3. **L3**: Direct generation (no VS)

## Trade-offs

| Dimension | VS Enabled | VS Disabled |
|---|---|---|
| Latency | +1 LLM call + NLI budget | Single LLM call |
| Diversity | k candidates | 1 candidate |
| Verifiability | NLI-scored | None |
| Cost | Higher (k× generation tokens + NLI) | Lower |
| Safety | Conservative routing on low prob | No routing |

## Magic Numbers

All numeric constants live in `src/reasoner/ara_vs_constants.py`. No literals are permitted in VS phase files.
