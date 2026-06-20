# VS Constants Decisions

> Approved: Day 11, Phase 3 — VS Foundation  
> All decisions frozen; numeric literals outside `ara_vs_constants.py` are prohibited.

---

## 1. k Defaults per Stage

| Stage | k | Rationale |
|---|---|---|
| Decomposition | 5 | Sufficient diversity without latency explosion |
| Generation | 5 | Sufficient diversity without latency explosion |
| Probes | 5 | Sufficient diversity without latency explosion |
| Coverage | 3 | Lower because coverage audit is additive, not primary |
| Claims | 5 | Sufficient diversity without latency explosion |
| Radiology Generation | 7 | Higher because medical tail-risk requires more candidates |

## 2. VSDeploymentProfile

| Profile | NLI Budget | Use Case |
|---|---|---|
| LATENCY_SENSITIVE | 1 | Real-time chat, low-latency APIs |
| BALANCED | 3 | Default for most pipelines |
| MAX_ACCURACY | 5 | Regulated verticals, safety-critical |

## 3. GenerationStrategy Default

`BEST_VERIFIABLE` is the default for regulated verticals. Safety-first: prefer candidates that can be independently verified over candidates that merely score highest on perplexity.

## 4. Tail Thresholds

| Vertical | Threshold | Rationale |
|---|---|---|
| Radiology | 0.10 | Medical imaging has noisy long-tail; 10% captures useful edge cases without overwhelming |
| Legal | 0.08 | Lower tolerance for hallucination in legal reasoning |
| Aerospace | 0.06 | Safety-critical; extremely tight tail tolerance |

## 5. JSON Parse Error Strategy

2 retries with temperature jitter, then direct fallback (return top candidate as plain text). Balances resilience against latency.

## 6. Calibration Weights

| Weight | Value | Role |
|---|---|---|
| W_ENTROPY | 0.30 | Candidate distribution diversity |
| W_SUPPORT | 0.25 | Cross-candidate overlap / consensus |
| W_NLI | 0.35 | Natural-language-inference verification score (highest because NLI is strongest signal) |
| W_RANK | 0.10 | Position bias / model rank preference |

Sum = 1.0 exactly.
