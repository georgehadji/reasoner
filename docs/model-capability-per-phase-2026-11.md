# Model evidence per dimension, November 2026 (as of 2026-11-09)

Read-only research. Prices and context are from the live catalogue (`openrouter_models.json`, 515 models), USD per million tokens. Evidence is web-sourced on 2026-11-09 (sources at the bottom).

## Read this first

- **Scores are INFERENCE unless stated.** Each 1-10 number is a mapping from one cited benchmark. No dimension has a direct benchmark except coding (SWE-bench Pro), long context (AA-LCR) and, partly, reasoning (AA Intelligence Index). U = UNKNOWN (no evidence found). Never read U as low.
- **Mapping used**
  - R (reasoning) from the AA Intelligence Index, new November scale: 59-60=9.5, 55=9, 50=8, 46=7.5, 40=7, 35=6, 30=5, 25=4, below 10=1-2.
  - Cd (coding) from SWE-bench Pro: 89.9=10, 80=9, 70=8, 65=7.5, 60=7, 55=6.5, 50=6.
  - LC (long context) from AA-LCR: 88=10, 85=9, 83=8.5, 82=8, 80=7.5.
  - W (writing) is a proxy from Arena Text Overall (1500+=9, 1485=8, 1475=7.5). Arena measures overall preference, not creative or long-form writing. No creative-writing board was readable (EQ-Bench loaded empty).
  - K (knowledge) from AA Omniscience where a value was shown (Gemini 4 Argon 4% hallucination, Opus 5.5 index 48). Most rows have only a delta from v1 to v1.1, which gives direction but no level.
  - Cr (creativity), CT (critical thinking), Co (consistency), J (JSON reliability) are U for almost every model. No public benchmark was found. CT is weakly proxied by hallucination rate and instruction following (IFBench).
- **The AA index scale has changed since the August doc.** Opus 5.5 is 59 now; the August doc had Opus 5 at 63 on v4.1.1. Do not compare November numbers with the August table. One snippet put the Mistral Large 4 preview at 38 on a v4.3.2 scale, which is not directly comparable to the leaderboard page.
- **AA scores are at the effort shown.** Max effort is slow. TTFT for Opus 5.5 (max) is 381s against 28s at high. GPT-6 Luna is 85s at max and 2.5s at low. For latency-sensitive roles, ask which effort OpenRouter serves.
- **Catalogue price anomalies. Re-verify before using for budgets.**
  - `moonshotai/kimi-k3`: in $0.192, out $16.
  - `z-ai/glm-5.2`: in $0.006, out $6.8.
  - `deepseek/deepseek-v4.1-flash-1017`: in $0.006.
  - `deepseek/deepseek-v4-pro-0813`: in $0.111, out $4.44.
  - `z-ai/glm-5.3`: in $0.07.
  - These look like cached-input or provider-promo artefacts, not list prices.
- **Reasoning leakage:** the only confirmed offender is `qwen/qwen3.5-flash-02-23` (user-confirmed, not re-tested here). A search for leakage reports on the new models found nothing. UNKNOWN does not mean clean. Leakage needs a live test with `response_format` on your own pipeline. Reasoning-model output on OpenRouter normally arrives in a separate reasoning field, so leakage is a provider or routing artefact.
- **Fixed-temperature behaviour:** no source found for any listed model. UNKNOWN for all. The Aug doc records empirical empty-content failures (`claude-sonnet` in `article_revise`, `gpt-5.1-codex-mini`). That is the kind of defect a paper review cannot clear.
- **Structured-output claims** below are capability flags from OpenRouter pages (supports `response_format` / tools). They are not reliability measurements.

## Table

Columns: id | lab | bloc | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | evidence and notes

### Anthropic (US)

| id | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | Evidence and notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-opus-5.5 | 4/20 | 1M | 9.5 | U | U | 9 | 10 | U | 8.5 | U | 9 | AA II 59 (max), 57 xhigh, 52 high. SWE-bench Pro 89.9 (#1). Arena 1506 (#4). AA-LCR 84.7. Omniscience index 48. #7 on OR usage. Cost per task $10 at max, $3.46 at high |
| anthropic/claude-opus-5 | 5/25 | 1M | U | U | U | 8 | 9 | U | U | U | U | SWE-Pro 79.2. Arena 1490. BenchLM overall 79.55. Superseded by 5.5 at a lower price |
| anthropic/claude-sonnet-5.5 | 2/10 | 1M | 9 | U | U | 8 | 9 | U | 8 | U | U | AA II 55 (max), 50 xhigh, 42 high, 31 medium. SWE-Pro 81.3. Arena 1473. AA-LCR 82.7. BenchLM 81.78. Strongest premium value. Omniscience delta -1.8 |
| anthropic/claude-fable-5.1 | 10/50 | 1M | 8 | U | U | 9 | 9 | U | 9 | U | 9 | AA II 50 (xhigh), 49 max. SWE-Pro 81.2. Arena 1503. AA-LCR 85.3. Omniscience accuracy 68% (highest shown). Costs 2.5x Opus 5.5 and scores lower on AA II. Writing role only |
| anthropic/claude-fable-5 | 10/50 | 1M | U | U | U | 9 | 9 | U | 8 | U | U | SWE-Pro 80. Arena 1504. AA-LCR 82.3. Dominated by 5.1 at the same price |
| anthropic/claude-haiku-5.5 | 0.1/0.5 | 1M | 6 | U | U | U | U | U | 8 | U | U | AA II 36 (max), 35 xhigh, 30 high. AA-LCR 82.7. BenchLM 66.43. Omniscience delta +1.6. TTFT 20s high, 183s max. Cost per task $0.16-0.41. Best 1M-context budget model on the evidence. Arena and SWE-Pro not found |

### OpenAI (US)

| id | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | Evidence and notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-astra | 10/50 | 1.05M | 9 | U | U | 7.5 | U | U | 7.5 | U | U | AA II 57 max, 55 xhigh/high, 52 medium. Arena 1474 (max). AA-LCR 80.7. BenchLM 85.80 (#3). Costs 5x Sol for a similar index. Omniscience delta -1.0 |
| openai/gpt-6.1-sol | 2/10 | 1.05M | 9 | U | U | 8 | U | U | 8.5 | U | U | AA II 55 max, 52 xhigh, 50 high, 46 medium. Cost per task $0.36-1.27, the cheapest per task of the top 15. Arena 1482. AA-LCR 83.0. BenchLM 85.35. Strongest value in the 50+ band |
| openai/gpt-6-sol | 2/10 | 1.05M | U | U | U | U | U | U | 8.5 | U | U | AA-LCR 83.7. BenchLM 78.09. No AA II row found. Superseded by 6.1-sol |
| openai/gpt-6.1-terra | 1/5 | 1.05M | 8 | U | U | U | U | U | 8.5 | U | U | AA II 51 max, 45 xhigh, 42 high, 38 medium, 31 non-reasoning. AA-LCR 82.7. BenchLM 80.72. Cost per task $0.07-0.96 |
| openai/gpt-6-luna | 0.1/0.5 | 1.05M | 4.5 | U | U | U | U | U | 8.5 | U | 4 | AA II 28 at max. AA-LCR 83.3. Omniscience delta -9.0 (weak recall). TTFT 85s max, 2.5s low. OR usage #5 (-25%) |
| openai/gpt-5.6-luna | 0.2/1.2 | 1.05M | U | U | U | U | 7 | U | 8.5 | U | U | SWE-Pro 62.7. AA-LCR 83.7. BenchLM 64.03. Dominated by gpt-6-luna on price |
| openai/gpt-6.1-*-pro, gpt-6-*-pro | as base | | U | U | U | U | U | U | U | U | U | No separate evidence found. Not shortlisted |

### Google (US)

| id | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | Evidence and notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| google/gemini-4-argon | 2/10 | 1M | 8 | U | U | 9.5 | U | U | U | U | 9 | AA II 50 (high). Arena 1522 (#2). Hallucination rate 4% on Omniscience. BenchLM 82.10. Cost per task $9.95 (token-heavy). Gemini 4 Carbon (Arena #1, II 60) is not in the catalogue |
| google/gemini-3.8-flash | 0.825/4.125 | 1M | 5 | U | U | 9 | U | U | 8 | U | U | AA II 31 high, 30 medium. Arena 1497 (#9, preliminary). AA-LCR 81.3. BenchLM 66.79. Cost per task $7.77 (very token-heavy) |
| google/gemini-3.7-flash | 0.75/3.75 | 1M | U | U | U | 8.5 | U | U | 8 | U | U | Arena 1489 (preliminary). AA-LCR 81.7. BenchLM 66.50. Aug doc had AA 56.0 on the old scale |
| google/gemini-2.5-flash-lite | 0.1/0.4 | 1M | U | U | U | U | U | U | U | U | 8 | Carried over from Aug doc: Vectara HHEM 3.3% hallucination. Vectara has not been updated for current flagships since May 2026 |

### xAI (US)

| id | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | Evidence and notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| x-ai/grok-4.7 | 2/6 | 500k | 6 | U | U | U | U | U | U | U | U | AA II 35 (xhigh/high), 31 low. Cost per task $6-8. Omniscience delta -0.8. Lowest index of the new releases, so not a shortlist leader |
| x-ai/grok-4.6 | 2/6 | 500k | U | U | U | U | U | U | 7.5 | U | U | AA-LCR 80.3. BenchLM 66.76 |
| x-ai/grok-4.20 | 1.25/2.5 | 2M | U | U | 8 | 7.5 | 6 | U | U | U | 8 | SWE-Pro 51.8. Arena 1474. IFBench 82.9. 2M context. Aug doc: 78% non-hallucination record, which I did not re-verify |
| x-ai/grok-4.3 | 1.25/2.5 | 1M | U | U | 8 | U | U | U | U | U | U | IFBench 83.3, the highest shown on the page |

### Chinese bloc

| id | lab | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | Evidence and notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| moonshotai/kimi-k3.1-pro | Moonshot | 2/10 | 1M | 7.5 | U | U | U | U | U | 9 | U | U | AA II 46. AA-LCR 86.3. BenchLM 75.03 (#12). Slow: 37.7 min per task, TTFT 167s. OR usage +91%, #9 |
| moonshotai/kimi-k3 | Moonshot | 0.192/16 (anomaly) | 1M | U | U | U | 8 | U | U | 10 | U | U | AA-LCR 88.7 (#1). Arena 1488. BenchLM 69.58. Check the price before use |
| deepseek/deepseek-v4.1-flash (and -1017) | DeepSeek | 0.051/0.567 (-1017: 0.006/0.5) | 1M | 5.5 | U | U | 7.5 | U | U | 8.5 | U | 3 | AA II 33 max, 29 high. Arena 1475 (-20260910, max). AA-LCR 84.0. BenchLM 65.41. Omniscience delta -3.8. Aug doc recorded 96% hallucination for v4-flash on closed-book recall. OR page lists tools and JSON-schema `response_format`. #1-2 by OR tokens (56T and 17.6T). TTFT 51s max, 24s high |
| deepseek/deepseek-v4-flash | DeepSeek | 0.091/0.182 | 1M | U | U | U | U | 6 | U | U | U | 3 | SWE-Pro 52.6 (0731). Cheapest at the 1M tier |
| deepseek/deepseek-v4-pro (0813) | DeepSeek | 0.894/1.788 (0813: 0.111/4.44) | 1M | U | U | U | U | 6.5 | U | 7.5 | U | U | SWE-Pro 55.4. AA-LCR 80.3. Not competitive with the V4.1 Flash on price |
| z-ai/glm-5.3 | Z.ai | 0.07/1.4 | 1M | 5 | U | U | 7.5 | U | U | U | U | 3 | AA II 32 (max). Arena 1483. $5.01 per task and 29.5 min. Omniscience delta -8.3. Overlaps with flash at 3x the output price |
| z-ai/glm-5.3-flash | Z.ai | 0.15/0.5 | 1M | 4.5 | U | U | 7.5 | U | U | U | U | U | AA II 28. Arena 1475. 45 min per task, TTFT 87s. OR #3 by tokens |
| z-ai/glm-5.2 | Z.ai | 0.006/6.8 (anomaly) | 1M | U | U | U | 7.5 | 7 | U | U | U | U | SWE-Pro 62.1. Arena 1475 (max). Check the price |
| qwen/qwen3.8-max-0902 | Alibaba | 2/6 | 1M | 5.5 | U | U | 7.5 | 7.5 | U | U | U | U | AA II 34. SWE-Pro 67.7 (Qwen3.8 Max). Arena 1484. BenchLM 64.85. Very slow: 60 min per task, $10 per task |
| qwen/qwen3.8-27b | Alibaba | 0.15/1.875 | 1M | U | U | U | U | 7 | U | 8 | U | U | SWE-Pro 61.7. AA-LCR 82.0 |
| qwen/qwen3.8-flash and -omni-flash | Alibaba | 0.15/0.47 | 1M | U | U | U | U | 7 | U | U | U | U | SWE-Pro 63.3 for Omni-Flash. 62.5 for "Flash-Next" (mapping to the catalogue id unverified). TTFT 93s for Flash-Next |
| qwen/qwen3.5-flash-02-23 | Alibaba | 0.065/0.26 | 1M | | | | | | | | **AVOID** | | **Reasoning leakage confirmed (user report). Disqualified for JSON roles** |
| xiaomi/mimo-v2.6-pro | Xiaomi | 0.435/0.87 | 1.05M | 5 | U | U | 7.5 | U | U | 9 | U | 2 | AA II 30. Arena 1480. AA-LCR 86.3. 39 min per task. Omniscience delta -12.9, so weak at recall. Cost per task $0.26, the cheapest of the 30-index models |
| minimax/minimax-m3.1-flash | MiniMax | 0.075/0.3 | 1M | 4.5 | U | U | U | U | U | U | U | 1 | AA II 29. Cost per task $0.49. Omniscience delta -22.0 (largest drop, so avoid for any fact-supplying role). OR #8 by tokens |
| minimax/minimax-m3 | MiniMax | 0.3/1.2 | 1M | U | U | 8 | U | 6 | U | 8.5 | U | U | IFBench 82.9. SWE-Pro 59. AA-LCR 83.0 |
| tencent/hy4 | Tencent | 0.417/1.25 | 1M | 6 | U | U | U | 7.5 | U | U | U | U | AA II 35. SWE-Pro 65.7 (preview, vendor-reported). TTFT 103s. Vendor claims are mostly internal benchmarks (11 of 14). Debuted #4 on OR tokens (new). Open-weight status disputed |
| tencent/hy3 | Tencent | 0.083/0.33 | 262k | U | U | U | U | U | U | U | U | U | Aug doc: anti-hallucination design. No new evidence |
| inclusionai/ling-3.1-flash | Ant Group | 0.045/0.135 | 1M | 5 | U | U | U | 8 | U | 8.5 | U | U | AA II 30 (1019). SWE-Pro 68.7 (surprisingly high for the price). AA-LCR 83.0. BenchLM 65.52. Cost per task $3.19 (token-hungry). Cheapest output price at 1M ctx |
| stepfun/step-5-preview | StepFun | 1/2.7 | 1M | 4.5 | U | U | U | U | U | 10 | U | U | AA II 29. AA-LCR 88.3 (#2). OR #6 by tokens. Preview status |
| meituan/longcat-2.0 | Meituan | 0.3/1.2 | 1M | U | U | U | U | U | U | U | U | U | No evidence found |

### Other

| id | lab / bloc | $in/out | ctx | R | Cr | CT | W | Cd | Co | LC | J | K | Evidence and notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| meta/muse-wonder | Meta (US) | 4/20 | 1M | 7 | U | U | 9.5 | U | U | 7.5 | U | U | AA II 44 max. Arena 1512 (#3). AA-LCR 80.7 (Full: 83.7, II 50). $6.95 per task |
| meta/muse-spark-1.3 | Meta (US) | 1.25/4.25 | 1M | U | U | U | 8.5 | U | U | 8.5 | U | U | Arena 1496 (#11). AA-LCR 83.0. SWE-Pro 61.5 for 1.1. BenchLM 65.67 for 1.1 |
| meta/muse-ember | Meta (US) | 0.1/0.5 | 1M | 6 | U | U | U | U | U | U | U | U | AA II 36 max, 34 xhigh. Cost per task $0.12-0.14. No latency data |
| mistralai/mistral-large-4-0 | Mistral (EU) | 0.7/2.1 | 1M | 6 | U | U | U | U | U | U | U | U | Preview 38 on a different index version. Press describes it as "a real jump that still lands mid-pack". Cyber Index 50. Weights not yet released. UNKNOWN on current AA leaderboard |
| mistralai/mistral-medium-3.5, mistral-small-2603 | Mistral (EU) | | | 1-2 | | | | | | | | | AA II 4-5. Not suitable for reasoning roles |
| cohere/command-a-plus | Cohere (CA) | 0.3/1.5 | 192k | 2 | U | U | U | U | U | U | U | U | AA II 6 (the page calls it among the least intelligent). 193 tok/s, TTFT 15s, very concise. 218B MoE, Apache 2.0. Fast but weak. Not for reasoning. A search snippet suggested a low hallucination rate but the page shows none, so unverified |
| nvidia/nemotron-3.5-super-vl | NVIDIA (US) | 0.15/0.5 | 1M | U | U | U | U | 6 | U | U | U | U | SWE-Pro 51.8 |
| perplexity/sonar, sonar-pro | Perplexity (US) | 1/1, 3/15 | 127k / 200k | U | U | U | U | U | U | U | U | U | Web-grounded. Carried over from Aug doc (SimpleQA 0.773 / 0.858). No new evidence |

## Operational

- **Latency:** AA publishes TTFT and time per task, not tokens per second, so there is no clean speed measure. A better proxy is time per task for roles that must return fast. Reasoning-heavy slow models (more than 30 min per task): Qwen3.8 Max, GLM-5.3-Flash, GLM-5.3, MiMo-V2.6-Pro, Kimi K3.1 Pro. Fastest per task among the high-index models: GPT-6.1 Sol and Terra (2.6-9 min), Haiku 5.5 high (6.5 min).
- **Token hunger:** some cheap-per-token models are expensive per task. Gemini 3.8 Flash costs $7.77 per task at index 31 and Ling 3.1 Flash costs $3.19. GPT-6.1 Terra and Sol cost under $1.30 for far higher index. Budget by per-task cost, not per-token price.
- **Popularity is not quality.** The OR top 10 by tokens is dominated by cheap DeepSeek V4.1 Flash, GLM 5.3 Flash, Hy4, GPT-6 Luna and Step 5 Preview. That is evidence of demand and uptime, not of correctness.

## Sources (all accessed 2026-11-09)

- Artificial Analysis leaderboard (II, cost per task, TTFT, time per task): https://artificialanalysis.ai/leaderboards/models
- AA Omniscience: https://artificialanalysis.ai/evaluations/omniscience
- AA IFBench: https://artificialanalysis.ai/evaluations/ifbench
- AA coding-agent index page (no model values readable): https://artificialanalysis.ai/models/capabilities/coding
- AA Command A+ page: https://artificialanalysis.ai/models/command-a-plus
- Arena Text leaderboard, snapshot 2026-11-08: https://arena.ai/leaderboard/text
- BenchLM SWE-bench Pro (updated 2026-11-09): https://benchlm.ai/benchmarks/swePro
- BenchLM AA-LCR (updated 2026-11-09): https://benchlm.ai/benchmarks/lcr
- BenchLM overall leaderboard (2026-11-09): https://benchlm.ai/
- OpenRouter rankings (usage through 2026-11-08): https://openrouter.ai/rankings
- OpenRouter DeepSeek V4.1 Flash: https://openrouter.ai/deepseek/deepseek-v4.1-flash
- Mistral Large 4 review: https://www.eesel.ai/blog/mistral-large-4-review
- Tencent Hy4 coverage: https://www.eesel.ai/blog/tencent-hy4-review and https://openrouter.ai/tencent/hy4-preview
- Vectara hallucination leaderboard (not updated for current flagships): https://github.com/vectara/hallucination-leaderboard
- Prior doc: `docs/model-capability-per-phase-2026-08.md`
- Unreadable and therefore not used: LiveBench (page returned no table), EQ-Bench Creative Writing (table empty), Aider (not found), AA coding agent index values.
