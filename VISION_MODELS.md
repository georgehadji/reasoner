# Vision-Capable LLM Models on OpenRouter — Complete Reference

> **Research Date:** April 20, 2026  
> **Source:** OpenRouter AI, provider docs, benchmark aggregators (Artificial Analysis, LangDB, CloudPrice)  
> **Scope:** All major multimodal (vision) models available via OpenRouter, with pricing, context, benchmarks, and Reasoner integration notes.

---

## Quick Reference Table

| Model | Provider | OpenRouter Path | Context | Input $/1M | Output $/1M | Vision | Audio | Video | Best For |
|---|---|---|---|---|---|---|---|---|---|
| **Claude Opus 4.7** | Anthropic | `anthropic/claude-opus-4.7` | 1M | $5.00 | $25.00 | ✅ | ❌ | ❌ | Frontier coding, async agents |
| **Claude Opus 4.6** | Anthropic | `anthropic/claude-opus-4.6` | 1M | $5.00 | $25.00 | ✅ | ❌ | ❌ | Complex refactors, knowledge work |
| **Claude Sonnet 5** | Anthropic | `anthropic/claude-sonnet-5` | 1M | $2.00 | $10.00 | ✅ | ❌ | ❌ | Default production, agents, coding, adaptive thinking |
| **Claude Haiku 4.5** | Anthropic | `anthropic/claude-haiku-4.5` | 200K | $1.00 | $5.00 | ✅ | ❌ | ❌ | High-volume, sub-agents, triage |
| **Gemini 3.1 Pro** | Google | `google/gemini-3.1-pro-preview` | 1M | $2.00 | $12.00 | ✅ | ✅ | ✅ | Frontier reasoning, agentic coding |
| **Gemini 3 Flash** | Google | `google/gemini-3-flash-preview` | 1M | $0.50 | $3.00 | ✅ | ✅ | ✅ | Agentic workflows, near-Pro speed |
| **Gemini 2.5 Pro** | Google | `google/gemini-2.5-pro` | 1M | $1.25 | $10.00 | ✅ | ✅ | ✅ | Complex reasoning, math, science |
| **Gemini 2.5 Flash** | Google | `google/gemini-2.5-flash` | 1M | $0.30 | $2.50 | ✅ | ✅ | ✅ | Workhorse reasoning, coding |
| **Gemini 2.5 Flash-Lite** | Google | `google/gemini-2.5-flash-lite` | 1M | $0.10 | $0.40 | ✅ | ✅ | ✅ | Ultra-low latency, cost efficiency |
| **GPT-5.4** | OpenAI | `openai/gpt-5.4` | 1M | $2.50 | $15.00 | ✅ | ❌ | ❌ | General-purpose, coding, document analysis |
| **GPT-5.4 Pro** | OpenAI | `openai/gpt-5.4-pro` | 1M | $30.00 | $180.00 | ✅ | ❌ | ❌ | Maximum reasoning, high-stakes |
| **GPT-5-mini** | OpenAI | `openai/gpt-5-mini` | 400K | $0.25 | $2.00 | ✅ | ❌ | ❌ | Lightweight reasoning, low latency |
| **o4-mini** | OpenAI | `openai/o4-mini` | 200K | $1.10 | $4.40 | ✅ | ❌ | ❌ | STEM, visual problem solving |
| **GPT-4o** | OpenAI | `openai/gpt-4o` | 128K | $2.50 | $10.00 | ✅ | ✅ | ❌ | Real-time voice, multilingual |
| **GLM-5.1** | Zhipu AI | `z-ai/glm-5.1` | 200K | $1.05 | $3.50 | ✅ | ❌ | ❌ | Coding + vision, 200K context, low hallucination |
| **GLM-4.6V** | Zhipu AI | `z-ai/glm-4.6v` | 128K | $0.30 | $0.90 | ✅ | ❌ | ❌ | Cheapest capable vision, screenshot-to-HTML |
| **Qwen3-VL 235B** | Alibaba | `qwen/qwen3-vl-235b-a22b-instruct` | 256K→1M | $0.20 | $0.88 | ✅ | ❌ | ✅ | GUI control, visual coding, video |
| **Kimi K2.6** | Moonshot | `moonshotai/kimi-k2.6` | 256K | $0.60 | $2.80 | ✅ | ❌ | ❌ | Agent swarm, coding-driven UI |
| **Kimi K2.5** | Moonshot | `moonshotai/kimi-k2.5` | 256K | $0.44 | $2.00 | ✅ | ❌ | ❌ | Visual coding, agent swarm, value |
| **MiniMax-01** | MiniMax | `minimax/minimax-01` | 1M | $0.20 | $1.10 | ✅ | ❌ | ❌ | Extreme long-context + vision |
| **MiMo V2 Omni** | Xiaomi | `xiaomi/mimo-v2-omni` | 256K | $0.40 | $2.00 | ✅ | ✅ | ✅ | True omni-modal (text/image/audio/video) |
| **Seed 1.6** | ByteDance | `bytedance-seed/seed-1.6` | 256K | $0.25 | $2.00 | ✅ | ❌ | ❌ | General multimodal workhorse |
| **Grok 4** | xAI | `x-ai/grok-4` | 256K | $3.00 | $15.00 | ✅ | ❌ | ❌ | Frontier benchmarks, web search |
| **Grok 4.1 Fast** | xAI | `x-ai/grok-4.1-fast` | 2M | $0.20 | $0.50 | ✅ | ❌ | ❌ | 2M context, agentic tools, value |
| **Gemma 3 27B** | Google | `google/gemma-3-27b-it` | 128K | $0.08 | $0.16 | ✅ | ❌ | ❌ | Best open-weight vision value |
| **Molmo 2 8B** | AllenAI | `allenai/molmo-2-8b` | 36K | $0.20 | $0.20 | ✅ | ❌ | ✅ | Video tracking SOTA, Apache 2.0 |

---

## 1. Anthropic Models

### Claude Opus 4.7
| Spec | Value |
|---|---|
| **OpenRouter Path** | `anthropic/claude-opus-4.7` |
| **Release** | April 16, 2026 |
| **Context** | 1,000,000 tokens |
| **Max Output** | 128,000 tokens |
| **Input** | $5.00 / 1M tokens |
| **Output** | $25.00 / 1M tokens |
| **Prompt Caching** | Read: $0.50 / 1M; Write: $6.25 / 1M |
| **Capabilities** | Vision (3.75 MP resolution — tripled from 4.6), reasoning, function calling, prompt caching, computer use, async agents |
| **Modality** | text + image → text |

**Benchmarks:**
- SWE-bench Pro: **64.3%** (up from 53.4% on 4.6)
- CursorBench: **70%** (up from 58%)
- Intelligence: 46.5+ (96th percentile)

**Notes:** Uses a new tokenizer that produces ~35% more tokens for the same input text vs. 4.6. Effective cost per request may rise despite identical rate card. US-only inference available at 1.1x pricing.

---

### Claude Opus 4.6
| Spec | Value |
|---|---|
| **OpenRouter Path** | `anthropic/claude-opus-4.6` |
| **Release** | February 4, 2026 |
| **Context** | 1,000,000 tokens |
| **Max Output** | 128,000 tokens |
| **Input** | $5.00 / 1M tokens |
| **Output** | $25.00 / 1M tokens |
| **Prompt Caching** | Read: $0.50 / 1M; Write: $6.25 / 1M |
| **Capabilities** | Vision, reasoning, function calling, prompt caching, coding, agentic workflows |

**Benchmarks:**
- Intelligence: 46.5 (96th percentile); Thinking: 53.0 (98th)
- Coding: 47.6 (97th percentile)
- GPQA: 84.0–91.3
- AAII: 46.4–46.5

---

### Claude Sonnet 5
| Spec | Value |
|---|---|
| **OpenRouter Path** | `anthropic/claude-sonnet-5` |
| **Release** | June 30, 2026 |
| **Context** | 1,000,000 tokens |
| **Max Output** | 128,000 tokens |
| **Input** | $2.00 / 1M tokens |
| **Output** | $10.00 / 1M tokens |
| **Prompt Caching** | Read: $0.20 / 1M; Write: $2.50 / 1M |
| **Capabilities** | Vision, reasoning, function calling, prompt caching, computer use, adaptive thinking (low, medium, high, max, x-high) |

**Benchmarks:**
- Intelligence: Anthropic's most capable Sonnet-class model with frontier performance
- Coding: major improvement over prior models
- Adaptive thinking: native reasoning effort level control

---

### Claude Haiku 4.5
| Spec | Value |
|---|---|
| **OpenRouter Path** | `anthropic/claude-haiku-4.5` |
| **Release** | October 15, 2025 |
| **Context** | 200,000 tokens |
| **Max Output** | 64,000 tokens |
| **Input** | $1.00 / 1M tokens |
| **Output** | $5.00 / 1M tokens |
| **Capabilities** | Vision, reasoning, function calling, prompt caching, extended thinking, computer use, context awareness |

**Benchmarks:**
- SWE-bench Verified: **>73%** (within ~5 points of Sonnet 4.5)
- OSWorld (computer use): **50.7%** — highest Haiku score ever
- First Haiku with extended thinking and computer use

---

## 2. Google Models

### Gemini 3.1 Pro Preview
| Spec | Value |
|---|---|
| **OpenRouter Path** | `google/gemini-3.1-pro-preview` |
| **Release** | February 19, 2026 |
| **Context** | 1,048,576 tokens (1M) |
| **Max Output** | 65,536 tokens |
| **Input** | $2.00 / 1M tokens |
| **Output** | $12.00 / 1M tokens |
| **Audio** | $2.00 / 1M tokens |
| **Capabilities** | Vision, audio, video, code, configurable reasoning (minimal/low/medium/high), tool calling, structured output, context caching |

**Benchmarks:**
- GPQA Diamond: **94.3%**
- SWE-Bench Verified: **80.6%**
- ARC-AGI-2: **77.1%**
- MMLU-Pro: ~89.8%
- AIME 2025: **91.2%**
- Humanity's Last Exam: 44.4% (no tools) / 51.4% (with tools)

---

### Gemini 3 Flash Preview
| Spec | Value |
|---|---|
| **OpenRouter Path** | `google/gemini-3-flash-preview` |
| **Release** | December 17, 2025 |
| **Context** | 1,048,576 tokens (1M) |
| **Max Output** | 65,536 tokens |
| **Input** | $0.50 / 1M tokens |
| **Output** | $3.00 / 1M tokens |
| **Audio** | $1.00 / 1M tokens |
| **Capabilities** | Vision, audio, video, PDF processing, configurable reasoning, tool calling, structured output, context caching |

**Benchmarks:**
- GPQA Diamond: **90.4%**
- AIME 2025: **99.7%**
- MMLU-Pro: **88.2%**
- SWE-Bench Verified: **78.0%**
- Near-Pro-level reasoning at substantially lower latency

---

### Gemini 2.5 Pro
| Spec | Value |
|---|---|
| **OpenRouter Path** | `google/gemini-2.5-pro` |
| **Release** | June 17, 2025 |
| **Context** | 1,048,576 tokens (1M) |
| **Max Output** | 65,536 tokens |
| **Input** | $1.25 / 1M tokens |
| **Output** | $10.00 / 1M tokens |
| **Audio** | $1.25 / 1M tokens |
| **Capabilities** | Vision, audio, video, code, advanced reasoning, tool calling, structured output |

**Benchmarks:**
- GPQA Diamond: ~83.7–86.4%
- AIME 2025: ~86.7–88.7%
- MMLU-Pro: ~83.7–86.2%
- MMMU (vision): ~79.6%
- SWE-Bench Verified: ~59.6%

---

### Gemini 2.5 Flash
| Spec | Value |
|---|---|
| **OpenRouter Path** | `google/gemini-2.5-flash` |
| **Release** | June 17, 2025 |
| **Context** | 1,048,576 tokens (1M) |
| **Max Output** | 65,535 tokens |
| **Input** | $0.30 / 1M tokens |
| **Output** | $2.50 / 1M tokens |
| **Audio** | $1.00 / 1M tokens |
| **Capabilities** | Vision, audio, video, PDF, built-in thinking (configurable), tool calling, JSON mode |

**Benchmarks:**
- GPQA Diamond: ~82.8%
- AIME 2025: ~84.3% (with thinking)
- MMLU-Pro: ~84.2% (with thinking)
- LMArena: First-place at release

---

### Gemini 2.5 Flash-Lite
| Spec | Value |
|---|---|
| **OpenRouter Path** | `google/gemini-2.5-flash-lite` |
| **Release** | July 22, 2025 |
| **Context** | 1,048,576 tokens (1M) |
| **Max Output** | 65,535 tokens |
| **Input** | $0.10 / 1M tokens |
| **Output** | $0.40 / 1M tokens |
| **Audio** | $0.30 / 1M tokens |
| **Capabilities** | Vision, audio, video, PDF, reasoning disabled by default (enable via API), tool calling, JSON mode |

**Benchmarks:**
- GPQA Diamond: ~64.6–70.9%
- MMMU (vision): ~72.9%
- Highest throughput in Gemini 2.5 family

---

### Gemma 3 27B
| Spec | Value |
|---|---|
| **OpenRouter Path** | `google/gemma-3-27b-it` (also `google/gemma-3-12b-it`, `google/gemma-3-4b-it`, `:free`) |
| **Release** | March 12, 2025 |
| **Context** | 131,072 tokens (128K) |
| **Max Output** | 8,000 tokens |
| **Input** | $0.08 / 1M tokens |
| **Output** | $0.16 / 1M tokens |
| **License** | Google Gemma License (open-weights, commercial allowed) |
| **Capabilities** | Vision, function calling, structured outputs, 140+ languages |

**Benchmarks:**
- MMLU-Pro: **67.5%**
- MMMU (vision): **64.9%**
- DocVQA: **85.6%**
- LMArena Elo: **1338**

---

## 3. OpenAI Models

### GPT-5.4
| Spec | Value |
|---|---|
| **OpenRouter Path** | `openai/gpt-5.4` |
| **Release** | March 5, 2026 |
| **Context** | 1,050,000 tokens (922K input / 128K output) |
| **Max Output** | 128,000 tokens |
| **Standard (≤272K)** | $2.50 input / $15.00 output |
| **Long (>272K)** | $5.00 input / $22.50 output |
| **Batch API** | $1.25 input / $7.50 output |
| **Cached** | $0.25 / 1M |
| **Capabilities** | Vision, text, PDF, tool use, structured outputs, reasoning, prompt caching |

**Benchmarks:**
- SWE-bench Verified: ~80%
- AIME 2025: ~88%
- ARC-AGI-2: ~73.3%
- OSWorld: ~75%
- Unifies Codex and GPT lines into single system

---

### GPT-5.4 Pro
| Spec | Value |
|---|---|
| **OpenRouter Path** | `openai/gpt-5.4-pro` |
| **Release** | March 5, 2026 |
| **Context** | 1,050,000 tokens |
| **Max Output** | 128,000 tokens |
| **Input** | $30.00 / 1M tokens |
| **Output** | $180.00 / 1M tokens |
| **Capabilities** | Vision, text, PDF, enhanced reasoning, tool use, structured outputs, reasoning efforts (default/minimal/xhigh) |

**Notes:** ~12× cost of standard GPT-5.4. Optimized for high-stakes reasoning, agentic coding, long-context workflows. Consistently outperforms on reasoning-heavy tasks when reasoning effort is high.

---

### GPT-5-mini
| Spec | Value |
|---|---|
| **OpenRouter Path** | `openai/gpt-5-mini` |
| **Release** | August 7, 2025 |
| **Context** | 400,000 tokens (272K input / 128K output) |
| **Max Output** | 128,000 tokens |
| **Input** | $0.25 / 1M tokens |
| **Output** | $2.00 / 1M tokens |
| **Cached** | $0.025 / 1M |
| **Capabilities** | Vision, reasoning, tool use, prompt caching |

**Benchmarks:**
- AIME 2025: ~91.1%
- GPQA: ~82.3%
- HMMT 2025: ~87.8%
- Humanity's Last Exam: ~16.7%

**Note:** Also exists: GPT-5.4-mini ($0.75/$4.50, 400K context, released Mar 2026) with SWE-bench Pro ~54.4%.

---

### o4-mini
| Spec | Value |
|---|---|
| **OpenRouter Path** | `openai/o4-mini` |
| **Release** | April 16, 2025 |
| **Context** | 200,000 tokens |
| **Max Output** | ~100,000 tokens |
| **Input** | $1.10 / 1M tokens |
| **Output** | $4.40 / 1M tokens |
| **Capabilities** | Vision, reasoning (explicit CoT), tool use, structured outputs, strong STEM |

**Benchmarks:**
- AIME 2024: ~93.4%
- AIME 2025: ~92.7%
- SWE-bench Verified: ~68.1%
- MathVista: ~84.3%
- MMMU: ~81.6%
- Codeforces ELO: ~2719

---

### GPT-4o
| Spec | Value |
|---|---|
| **OpenRouter Path** | `openai/gpt-4o` |
| **Release** | May 13, 2024 |
| **Context** | 128,000 tokens |
| **Max Output** | 16,384 tokens |
| **Input** | $2.50 / 1M tokens |
| **Output** | $10.00 / 1M tokens |
| **Cached** | $1.25 / 1M |
| **Capabilities** | Vision, audio input/output (real-time voice), text, function calling, multilingual |

**Benchmarks:**
- MMLU: ~88.7%
- MATH: ~76.6–82.9%
- HumanEval: ~87.1–90.2%
- GSM8K: ~95.3%

---

## 4. Chinese Models

### GLM-5.1 (Zhipu AI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `z-ai/glm-5.1` |
| **Release** | April 7, 2026 |
| **Architecture** | 744B MoE, 40B active, 256 experts, 8 active/token |
| **Context** | 202,752 tokens (~203K) |
| **Max Output** | 66,000 tokens |
| **Input** | ~$0.70–$1.05 / 1M tokens (OpenRouter ~$0.698) |
| **Output** | ~$3.50–$4.40 / 1M tokens (OpenRouter ~$4.40) |
| **License** | MIT (open-weights) |
| **Capabilities** | Vision (Image + PDF), reasoning, function calling, prompt caching, long-horizon autonomy (8+ hour tasks) |
| **Training** | 100,000 Huawei Ascend 910B chips (no Nvidia) |

**Benchmarks:**
- SWE-Bench Pro: **58.4%** (beats GPT-5.4 & Claude Opus 4.6)
- AIME 2026: **95.3%**
- Intelligence Index: **51.4** (#9)
- TAU2: **1.0** (#6)
- Coding Index: **43.4** (#20)
- Hallucination rate: **~34%** (lowest among open models)

---

### GLM-4.6V (Zhipu AI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `z-ai/glm-4.6v` |
| **Release** | December 8, 2025 |
| **Context** | 131,072 tokens |
| **Max Output** | 131,072 tokens |
| **Input** | $0.30 / 1M tokens |
| **Output** | $0.90 / 1M tokens |
| **License** | Open-source weights |
| **Capabilities** | Vision (images, documents, charts), reasoning, function calling, structured outputs, prompt caching, screenshot-to-HTML, UI reconstruction |

**Benchmarks:**
- AA Math Index: **85.3**
- GPQA: **71.9%**
- MMLU-Pro: **79.9%**
- AA Intelligence: **53.1**
- First model to pass images as tool inputs

---

### Qwen3-VL 235B (Alibaba)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `qwen/qwen3-vl-235b-a22b-instruct` (flagship)  
`qwen/qwen3-vl-235b-a22b-thinking` (reasoning)  
`qwen/qwen3-vl-30b-a3b-instruct` (mid)  
`qwen/qwen3-vl-8b-instruct` (compact) |
| **Release** | Sep 23, 2025 (235B); Oct 6, 2025 (30B); Oct 14, 2025 (8B) |
| **Context** | 262,144 tokens (native; extensible to 1M on some variants) |
| **Max Output** | ~33,000 tokens |
| **235B Instruct** | $0.20 input / $0.88 output |
| **235B Thinking** | $0.26 input / $2.60 output |
| **30B** | $0.13 input / $0.52 output |
| **8B** | ~$0.06–$0.14 input / ~$0.40–$0.63 output |
| **Architecture** | MoE (235B total / ~22B active for flagship) |
| **Capabilities** | Vision (images + video), function calling, tools, structured outputs, GUI control, visual coding, 32-language OCR, 2D/3D spatial grounding, multi-hour video understanding |

**Benchmarks:**
- MMLU: **88.8%**
- MMLU-Pro: **82.0%**
- GPQA: **71.2%**
- LiveCodeBench: **59.4%**

---

### Kimi K2.6 (Moonshot AI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `moonshotai/kimi-k2.6` |
| **Release** | April 20, 2026 |
| **Architecture** | 1T MoE, 32B active, 256K context |
| **Context** | 262,144 tokens |
| **Max Output** | ~65K–131K (expected) |
| **Input** | $0.60 / 1M tokens |
| **Output** | $2.80 / 1M tokens |
| **Capabilities** | Vision (multimodal), multi-agent orchestration, coding-driven UI/UX generation, reasoning |
| **Modes** | Thinking (temp=1.0) and Instant (temp=0.6) |

**Benchmarks:**
- Too new for extensive public benchmarks
- Positioned as Moonshot's new flagship for long-horizon coding and agentic workflows
- Native multimodal agentic model with MoonViT vision encoder (400M)

---

### Kimi K2.5 (Moonshot AI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `moonshotai/kimi-k2.5` |
| **Release** | January 27, 2026 |
| **Architecture** | 1T MoE, 32B active |
| **Context** | 262,144 tokens |
| **Max Output** | 65,535 tokens |
| **Input** | ~$0.38–$0.60 / 1M (OpenRouter ~$0.38) |
| **Output** | ~$1.72–$3.00 / 1M (OpenRouter ~$1.72) |
| **License** | Modified MIT (open-source) |
| **Capabilities** | Vision (native multimodal), reasoning, function calling, agent swarm (self-directed multi-agent), visual coding |
| **Cache Discount** | Up to 75% discount for cached context |

**Benchmarks:**
- SWE-Bench Verified: **76.8%**
- AIME 2025: **96.1%**
- BrowseComp: **78.4%**
- MMMU Pro: **78.5%**
- VideoMMU: **86.6%**

---

### MiniMax-01 (MiniMax)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `minimax/minimax-01` |
| **Release** | January 15, 2025 |
| **Architecture** | 456B MoE, 45.9B active. Hybrid Lightning Attention + Softmax Attention + MoE |
| **Context** | 1,000,192 tokens (1M) |
| **Max Output** | 1,000,000 tokens |
| **Input** | $0.20 / 1M tokens |
| **Output** | $1.10 / 1M tokens |
| **Capabilities** | Vision (text + image), extreme long-context (1M+) |

**Notes:** Combines MiniMax-Text-01 and MiniMax-VL-01. Vision-capable flagship. Other MiniMax models (M2, M2.5, M2.7) are text-only.

**Benchmarks:**
- LongBench v2: **56.5%** (w/ CoT) — beats GPT-4o, Claude 3.5 Sonnet, Qwen2.5-72B

---

### MiMo V2 Omni (Xiaomi)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `xiaomi/mimo-v2-omni` |
| **Release** | March 18, 2026 |
| **Context** | 262,144 tokens |
| **Max Output** | ~32,000 tokens |
| **Input** | $0.40 / 1M tokens |
| **Output** | $2.00 / 1M tokens |
| **Capabilities** | **True omni-modal**: Text + Image + Video + Audio. Reasoning, tools, code execution, visual grounding. Industry-first 10+ hours continuous audio understanding. Unified architecture (not stitched pipelines). |

**Benchmarks:**
- GPQA Diamond: **82.8%**
- Humanity's Last Exam: **19.9%**
- τ²-Bench (tool use/agents): **91.2%**
- BigBench Audio: **94.0** (leads all models)
- MMAU-Pro (audio): **69.4** (tops audio leaderboard)
- FutureOmni (video): **66.7%**
- AA Intelligence: **43.4**

---

### ByteDance Seed 1.6
| Spec | Value |
|---|---|
| **OpenRouter Path** | `bytedance-seed/seed-1.6` |
| **Release** | December 23, 2025 |
| **Architecture** | 230B MoE, 23B active |
| **Context** | 262,144 tokens |
| **Max Output** | ~33,000 tokens |
| **Input** | $0.25 / 1M tokens |
| **Output** | $2.00 / 1M tokens |
| **Capabilities** | Vision (text + image), reasoning, tools, adaptive deep thinking |

**Variants:**
- **Seed 1.6 Flash**: $0.075/$0.30, 16K output, ultra-fast

**Benchmarks:**
- Evalry avg: **90.0%** (early data, limited runs)
- General-purpose multimodal workhorse

---

## 5. Other Notable Models

### Grok 4 (xAI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `x-ai/grok-4` |
| **Release** | July 9, 2025 |
| **Context** | 256,000 tokens |
| **Max Output** | 256,000 tokens |
| **Input** | $3.00 / 1M tokens |
| **Output** | $15.00 / 1M tokens |
| **Capabilities** | Vision, reasoning, native tool use, web/X search, code execution, function calling, agentic workflows |

**Benchmarks:**
- MMLU-Pro: **86.6%**
- GPQA Diamond: **87.7%**
- MATH-500: **99.0%**
- AIME 2024: **94.3%**
- LiveCodeBench: **81.9%**
- SWE-bench Verified: **69.1%**
- Humanity's Last Exam: **23.9%**

---

### Grok 4.1 Fast (xAI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `x-ai/grok-4.1-fast` (also `:free`) |
| **Release** | November 19, 2025 |
| **Context** | 2,000,000 tokens (2M) |
| **Max Output** | 30,000 tokens |
| **Input** | $0.20 / 1M tokens |
| **Output** | $0.50 / 1M tokens |
| **Capabilities** | Vision, reasoning/non-reasoning variants, agentic tool calling, 2M context, code execution, web/X search |

**Benchmarks:**
- Quality score: **64** (near frontier, matching o3)
- BFCL-V4: **72%**
- τ²-bench Telecom: **100%**

---

### Molmo 2 8B (AllenAI)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `allenai/molmo-2-8b` (also `:free`) |
| **Release** | January 9, 2026 |
| **Context** | 36,864 tokens |
| **Input** | $0.20 / 1M tokens |
| **Output** | $0.20 / 1M tokens |
| **License** | Apache 2.0 (fully open source) |
| **Capabilities** | Vision (images, video, multi-image), spatial/temporal grounding, object pointing & tracking, dense captioning |
| **Architecture** | Based on Qwen3-8B with SigLIP 2 vision backbone |

**Benchmarks:**
- SOTA among open-weight models on **video tracking** (beats Gemini 3 Pro)
- SOTA on **short-video QA** and **video counting**
- Outperforms original Molmo 72B on image pointing/grounding
- Trained on only 9.19M videos

---

### Devstral 2 (Mistral)
| Spec | Value |
|---|---|
| **OpenRouter Path** | `mistralai/devstral-2512` (also `:free`) |
| **Release** | December 9, 2025 |
| **Context** | 262,144 tokens (256K) |
| **Input** | $0.40 / 1M tokens |
| **Output** | $2.00 / 1M tokens |
| **License** | Modified MIT (123B); Apache 2.0 (Small 24B) |
| **Capabilities** | Devstral Small 2 (24B) supports image input; 123B is text-only. Agentic coding, tool calling, multi-file codebase exploration |

**Benchmarks:**
- SWE-bench Verified: **72.2%** (top open-weight coding model)
- Intelligence Index: 22.0 (54th percentile)
- Mistral claims 7× lower cost than Claude Sonnet for comparable tasks

---

## 6. Best Models by Use Case

| Use Case | Top Pick | Runner-up | Budget Pick |
|---|---|---|---|
| **Frontier coding + vision** | Claude Opus 4.7 | GLM-5.1 | Kimi K2.5 |
| **General production default** | Claude Sonnet 5 | GPT-5.4 | Gemini 2.5 Flash |
| **Ultra-low latency vision** | Gemini 2.5 Flash-Lite | Grok 4.1 Fast | Gemma 3 27B |
| **Maximum context + vision** | Grok 4.1 Fast (2M) | MiniMax-01 (1M) | Gemini 3 Flash (1M) |
| **Audio + video + vision** | MiMo V2 Omni | Gemini 3.1 Pro | Gemini 3 Flash |
| **Cheapest vision** | Gemma 3 27B ($0.08) | GLM-4.6V ($0.30) | MiniMax-01 ($0.20) |
| **Open-source vision** | Molmo 2 (Apache 2.0) | Gemma 3 (Gemma License) | Qwen3-VL 8B |
| **Scientific reasoning + vision** | Gemini 3.1 Pro | Claude Opus 4.7 | o4-mini |
| **Agent swarm + vision** | Kimi K2.6 | Kimi K2.5 | Grok 4.1 Fast |
| **Honest/low hallucination** | GLM-5.1 (~34%) | Claude Sonnet 5 | — |
| **GUI control + visual coding** | Qwen3-VL 235B | Kimi K2.5 | — |
| **Video understanding** | Molmo 2 | Qwen3-VL 235B | Gemini 2.5 Flash |

---

## 7. Reasoner Integration Notes

### Vision-Capable Models Already in Reasoner Registry
| Reasoner ID | OpenRouter Path | Vision? |
|---|---|---|
| `claude-sonnet` | `anthropic/claude-sonnet-5` | ✅ |
| `claude-opus` | `qwen/qwen3.6-plus` (alias) | ❌ (wrong alias) |
| `gpt-5` | `openai/gpt-5.4` | ✅ |
| `gpt-5-mini` | `openai/gpt-5.4-mini` | ✅ |
| `gemini-pro` | `google/gemini-2.5-pro` | ✅ |
| `gemini-flash` | `google/gemini-2.5-flash` | ✅ |
| `kimi-k2-5` | `moonshotai/kimi-k2.5` | ✅ |
| `kimi-k2-6` | `moonshotai/kimi-k2.6` | ✅ |
| `glm-5` | `z-ai/glm-5` | ❌ (text-only, vision via tools) |
| `glm-5.1` | `z-ai/glm-5.1` | ✅ |
| `glm-4-airx` | `z-ai/glm-4.6` | ❌ (text-only variant) |
| `grok-4.20` | `x-ai/grok-4.20` | Need to verify |
| `grok-4` | `x-ai/grok-4` | ✅ |

### Models to Add for Vision Support
| Reasoner ID | OpenRouter Path | Why Add |
|---|---|---|
| `gemini-3-flash` | `google/gemini-3-flash-preview` | 1M context, $0.50/$3.00, PDF+video+vision |
| `gemini-3-pro` | `google/gemini-3.1-pro-preview` | Frontier reasoning, $2/$12, best scientific |
| `gemini-2.5-flash-lite` | `google/gemini-2.5-flash-lite` | Cheapest 1M context vision at $0.10/$0.40 |
| `glm-4.6v` | `z-ai/glm-4.6v` | Cheapest capable vision at $0.30/$0.90 |
| `qwen3-vl` | `qwen/qwen3-vl-235b-a22b-instruct` | GUI control, visual coding, video |
| `minimax-01` | `minimax/minimax-01` | 1M context vision at $0.20/$1.10 |
| `mimo-v2-omni` | `xiaomi/mimo-v2-omni` | Only true omni-modal (audio+video+image) |
| `grok-4.1-fast` | `x-ai/grok-4.1-fast` | 2M context vision at $0.20/$0.50 |
| `gemma-3-27b` | `google/gemma-3-27b-it` | Open-weight vision at $0.08/$0.16 |

### Implementation Strategy for Reasoner
1. **Phase 1 (Text Extraction)**: Works with ALL models — use `pypdf` + cheap vision model (Gemini Flash or GLM-4.6V) to caption images, inject text into prompt
2. **Phase 2 (Native Multimodal)**: For presets using vision-capable models, pass `image_url` directly via OpenRouter API. Models that support this:
   - Claude Sonnet 4.6, Opus 4.6/4.7, Haiku 4.5
   - Gemini 2.5/3.0/3.1 family (all variants)
   - GPT-5.4, GPT-5-mini, o4-mini, GPT-4o
   - GLM-5.1, GLM-4.6V
   - Kimi K2.5, Kimi K2.6
   - Qwen3-VL
   - Grok 4, Grok 4.1 Fast
   - MiniMax-01
   - Gemma 3

### Cost-Optimized Vision Routing
| Budget Tier | Vision Model | Cost |
|---|---|---|---|
| Ultra-budget | Gemma 3 27B / `:free` | $0.08 or FREE |
| Budget | Gemini 2.5 Flash-Lite | $0.10/$0.40 |
| Balanced | GLM-4.6V / MiniMax-01 | $0.20/$0.90–$1.10 |
| Premium | Claude Sonnet 4.6 / GPT-5.4 | $2.50–$3.00/$12–$15 |
| Frontier | Claude Opus 4.7 / Gemini 3.1 Pro | $5.00/$25.00 |
