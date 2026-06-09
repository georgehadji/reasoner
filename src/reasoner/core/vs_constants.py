"""Verbalized Sampling constants — zero magic numbers outside this file."""
from __future__ import annotations

# Stage k defaults
VS_K_DECOMPOSITION = 5
VS_K_GENERATION = 5
VS_K_PROBES = 5
VS_K_COVERAGE = 3
VS_K_CLAIMS = 5
VS_K_RADIOLOGY_GENERATION = 7

# Tail thresholds per vertical
VS_TAIL_THRESHOLD_RADIOLOGY = 0.10
VS_TAIL_THRESHOLD_LEGAL = 0.08
VS_TAIL_THRESHOLD_AEROSPACE = 0.06

# Routing thresholds
VS_ROUTING_HIGH_PROB = 0.70
VS_ROUTING_MEDIUM_PROB = 0.30

# Calibration weights (must sum to 1.0)
W_ENTROPY = 0.30
W_SUPPORT = 0.25
W_NLI = 0.35
W_RANK = 0.10

# Operational
VS_PARSE_MAX_RETRIES = 2
VS_CONSENSUS_MIN_SUPPORT = 2
VS_PROBE_MIN_SEMANTIC_DISTANCE = 0.15

# Feature flags (all default True)
VS_PROBE_GENERATION_ENABLED = True
VS_DECOMPOSITION_ENABLED = True
VS_COVERAGE_AUDIT_ENABLED = True
VS_GENERATION_ENABLED = True
VS_CALIBRATION_ENABLED = True
VS_CLAIM_EXTRACTION_ENABLED = True
VS_VERIFICATION_ROUTING_ENABLED = True
VS_CONFLICT_SURFACING_ENABLED = True
VS_BEHAVIORAL_AUDIT_ENABLED = True

# Structured log keys
LOG_VS_ENTROPY = "vs_entropy"
LOG_VS_STRATEGY = "vs_strategy"
LOG_VS_CANDIDATE_RANK = "vs_candidate_rank"
LOG_VS_PROBE_DOMAIN = "vs_probe_domain"
LOG_VS_PROBE_COUNT = "vs_probe_count"
LOG_VS_NLI_SCORES = "vs_nli_scores"
LOG_VS_K = "vs_k"
LOG_VS_MODE_COLLAPSE = "vs_mode_collapse"

# Deployment profiles
class VSDeploymentProfile:
    LATENCY_SENSITIVE = "latency_sensitive"
    BALANCED = "balanced"
    MAX_ACCURACY = "max_accuracy"

PROFILE_NLI_BUDGET = {
    VSDeploymentProfile.LATENCY_SENSITIVE: 1,
    VSDeploymentProfile.BALANCED: 3,
    VSDeploymentProfile.MAX_ACCURACY: 5,
}
