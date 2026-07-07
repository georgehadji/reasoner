# Reasoner — Methods & Presets Reference

**Total presets:** 50  
**Total methods:** 24  
**Last updated:** 2026-07-05

---

## Methods

| # | Method | Presets | Purpose |
|---|--------|---------|---------|
| 1 | `analogical` | 2 | Cross-domain analogy mapping and transfer |
| 2 | `article` | 2 | 10-phase publication-grade editorial pipeline with voice-consistent models |
| 3 | `bayesian` | 2 | Prior→likelihood→posterior→sensitivity reasoning |
| 4 | `brainstorming` | 2 | Verbalized Sampling: multi-round divergent + convergent ideation |
| 5 | `coding` | 2 | 5-phase production code: spec→generate→review→test→assemble |
| 6 | `cove` | 2 | Chain-of-Verification: draft→verify→answer→revise |
| 7 | `cross-language` | 2 | DeepL-powered cross-language reasoning |
| 8 | `debate` | 2 | Two-model adversarial debate with judging |
| 9 | `delphi` | 2 | Multi-round expert consensus with convergence tracking |
| 10 | `dialectical` | 2 | Hegelian thesis→antithesis→synthesis |
| 11 | `image-gen` | 2 | Image generation and prompt engineering |
| 12 | `iterative-critique` | 2 | Adversarial generator-critic convergence loop |
| 13 | `jury` | 2 | Multi-generator panel scored by independent critics |
| 14 | `multi-perspective` | 4 | Default: multi-perspective generation across diverse labs |
| 15 | `pot` | 2 | Program-of-Thought: executable code as intermediate reasoning |
| 16 | `pre-mortem` | 2 | Prospective hindsight failure analysis |
| 17 | `research` | 2 | Web-grounded deep research with iterative search |
| 18 | `scientific` | 2 | Hypothesis→falsification→evidence→synthesis |
| 19 | `self-discover` | 2 | Dynamic selection and composition of reasoning modules |
| 20 | `socratic` | 2 | Elenchus questioning to expose hidden assumptions |
| 21 | `sot` | 2 | Skeleton-of-Thought: skeleton→parallel solve→assemble |
| 22 | `subagent` | 2 | Per-subagent routing with dedicated cross-lab models |
| 23 | `tot` | 2 | Tree-of-Thoughts: tree search with backtracking |
| 24 | `writing` | 2 | Research-backed writing via CoVE+SoT+Pre-Mortem |

---

## Presets by Method

### analogical

#### `analogical-budget` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `analogical-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### article

#### `article-budget` — 12 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `sonar` | perplexity/sonar | perplexity |
| synthesis | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| writing_draft | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| writing_factcheck | `sonar` | perplexity/sonar | perplexity |
| writing_assemble | `gpt-4o-mini` | openai/gpt-4o-mini | openai |
| article_sot_skeleton | `gpt-4o-mini` | openai/gpt-4o-mini | openai |
| article_critic | `hy3` | nousresearch/hy3 | tencent |
| article_revise | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| article_humanize | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| article_verifier | `hy3` | qwen/hy3-02-23 | tencent |
| post_synthesis_verify | `sonar` | perplexity/sonar | perplexity |

#### `article-premium` — 13 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `sonar-pro` | perplexity/sonar-pro | perplexity |
| synthesis | `qwen3.7-max` | qwen/qwen3.7-max | qwen |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| writing_draft | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| writing_factcheck | `sonar-pro` | perplexity/sonar-pro | perplexity |
| writing_outline | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| writing_assemble | `gpt-4o-mini` | openai/gpt-4o-mini | openai |
| article_sot_skeleton | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| article_critic | `grok-4.3` | x-ai/grok-4.3 | xai |
| article_revise | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| article_humanize | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| article_verifier | `qwen3.7-max` | qwen/qwen3.7-max | qwen |
| post_synthesis_verify | `sonar-pro` | perplexity/sonar-pro | perplexity |

### bayesian

#### `bayesian-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-haiku` | anthropic/claude-haiku-4.5 | anthropic |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `bayesian-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### brainstorming

#### `brainstorming-budget` — 8 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-haiku` | anthropic/claude-haiku-4.5 | anthropic |
| brainstorm_cluster | `google/gemma-2-9b-it` | google/gemma-3-12b-it | google |
| brainstorm_develop | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `brainstorming-premium` — 9 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| brainstorm_cluster | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| brainstorm_develop | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### coding

#### `coding-budget` — 10 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `qwen3-coder-flash` | qwen/qwen3-coder-flash | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| coding_assemble | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| coding_review | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| coding_spec | `qwen3-coder-flash` | qwen/qwen3-coder-flash | qwen |
| coding_tests | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |

#### `coding-premium` — 11 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| coding_assemble | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| coding_review | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| coding_spec | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| coding_tests | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| deep_read | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| verifier | `glm-5.2` | z-ai/glm-5.2 | zhipu |

### cove

#### `cove-budget` — 9 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| cove_answer | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| cove_revise | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| cove_verify | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `cove-premium` — 10 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| cove_answer | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| cove_revise | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| cove_verify | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### cross-language

#### `cross-language-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `cross-language-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `glm-5.2` | z-ai/glm-5.2 | zhipu |

### debate

#### `debate-budget` — 9 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash` | google/gemini-3.5-flash | google |
| constructive | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| destructive | `gpt-oss-120b` | openai/gpt-oss-120b | openai |
| systemic | `gemini-flash` | google/gemini-3.5-flash | google |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `debate-premium` — 9 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| constructive | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| destructive | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| systemic | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### delphi

#### `delphi-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `delphi-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### dialectical

#### `dialectical-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `dialectical-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### image-gen

#### `image-gen-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash` | google/gemini-3.5-flash | google |
| image_generate | `gemini-3.1-flash-lite-image` | google/gemini-3.1-flash-lite-image | google |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `image-gen-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| image_generate | `gemini-pro-image` | google/gemini-3-pro-image-preview | google |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### iterative-critique

#### `iterative-critique-budget` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `grok-4.3` | x-ai/grok-4.3 | xai |
| synthesis | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `mistral-small-2603` | mistralai/mistral-small-2603 | mistral |
| scoring | `qwen3.6-flash` | qwen/qwen3.6-flash | qwen |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `gemini-flash-lite-real` | google/gemini-3.1-flash-lite | google |

#### `iterative-critique-premium` — 8 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `mistral-large-3` | mistralai/mistral-large-2512 | mistral |
| meta_evaluator | `kimi-k2-6` | moonshotai/kimi-k2.6 | moonshot |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |

### jury

#### `jury-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `jury-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### multi-perspective

#### `multi-perspective-budget` — 12 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash` | google/gemini-3.5-flash | google |
| perspective_cot | `mimo-v2.5` | xiaomi/mimo-v2.5 | xiaomi |
| perspective_analysis | `qwen3.6-flash` | qwen/qwen3.6-flash | qwen |
| constructive | `deepseek-v3` | deepseek/deepseek-v3.2 | deepseek |
| destructive | `hermes-4-70b` | nousresearch/hermes-4-70b | nousresearch |
| systemic | `hy3` | qwen/hy3 | tencent |
| minimalist | `ministral-8b` | mistralai/mistral-small-3.2-24b-instruct | mistral |
| synthesis | `qwen3-max` | qwen/qwen3.7-plus | qwen |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `hy3` | openai/hy3 | tencent |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `multi-perspective-premium` — 14 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| perspective_cot | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| perspective_analysis | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| constructive | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| destructive | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| systemic | `qwen3.7-max` | qwen/qwen3.7-max | qwen |
| minimalist | `mistral-large-3` | mistralai/mistral-large-2512 | mistral |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

#### `multi-perspective-ultra-budget` — 12 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| perspective_cot | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| perspective_analysis | `qwen3.6-flash` | qwen/qwen3.6-flash | qwen |
| constructive | `stepfun-3.7-flash` | stepfun/step-3.7-flash | stepfun |
| destructive | `ling-2.6-flash-free` | inclusionai/ling-2.6-flash | inclusionai |
| systemic | `gpt-oss-20b` | openai/gpt-oss-20b | openai |
| minimalist | `ministral-8b` | mistralai/mistral-small-3.2-24b-instruct | mistral |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `nvidia-nemotron-test` — 3 roles (experimental)
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `nvidia-nemotron-super` | nvidia/nemotron-3-super-120b-a12b | nvidia |
| perspective_cot | `nvidia-nemotron-super` | nvidia/nemotron-3-super-120b-a12b | nvidia |
| perspective_analysis | `nvidia-nemotron-super` | nvidia/nemotron-3-super-120b-a12b | nvidia |
| synthesis | `nvidia-nemotron-super` | nvidia/nemotron-3-super-120b-a12b | nvidia |

### pot

#### `pot-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `pot-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### pre-mortem

#### `pre-mortem-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `pre-mortem-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### research

#### `research-budget` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-haiku` | anthropic/claude-haiku-4.5 | anthropic |
| synthesis | `hy3` | openai/hy3 | tencent |
| deep_read | `sonar-pro-search` | perplexity/sonar-pro-search | perplexity |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `research-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| deep_read | `sonar-reasoning-pro` | perplexity/sonar-reasoning-pro | perplexity |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `sonar-deep-research` | perplexity/sonar-deep-research | perplexity |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### scientific

#### `scientific-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `claude-haiku` | anthropic/claude-haiku-4.5 | anthropic |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `qwen3.6-flash` | qwen/qwen3.6-flash | qwen |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `scientific-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### self-discover

#### `self-discover-budget` — 9 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| sd_adapt | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| sd_implement | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| sd_select | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `self-discover-premium` — 10 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| sd_adapt | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| sd_implement | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| sd_select | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### socratic

#### `socratic-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `socratic-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### sot

#### `sot-budget` — 6 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `sot-premium` — 7 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### subagent

#### `subagent-budget` — 11 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| subagent_critique_bias | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| subagent_critique_counter | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| subagent_critique_evidence | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| subagent_critique_logic | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| subagent_decomposition | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| verifier | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |

#### `subagent-premium` — 11 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `qwen3.7-max` | qwen/qwen3.7-max | qwen |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| subagent_critique_bias | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| subagent_critique_counter | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| subagent_critique_evidence | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| subagent_critique_logic | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| subagent_decomposition | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| verifier | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |

### tot

#### `tot-budget` — 9 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| tot_backtrack | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| tot_decompose | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| tot_evaluate | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| verifier | `qwen3.5-flash` | qwen/qwen3.5-flash-02-23 | qwen |

#### `tot-premium` — 10 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `gemini-pro-real` | google/gemini-3.1-pro-preview | google |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `minimax-m3` | minimax/minimax-m3 | minimax |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `grok-4.3` | x-ai/grok-4.3 | xai |
| tot_backtrack | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| tot_decompose | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| tot_evaluate | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| verifier | `grok-4.3` | x-ai/grok-4.3 | xai |

### writing

#### `writing-budget` — 10 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-flash-lite` | qwen/qwen3.5-flash-02-23 | qwen |
| synthesis | `hy3` | openai/hy3 | tencent |
| fusion | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| meta_evaluator | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |
| scoring | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| stress_testing | `ring-2.6-1t` | inclusionai/ring-2.6-1t | inclusionai |
| verifier | `qwen3.7-plus` | qwen/qwen3.7-plus | qwen |
| writing_assemble | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| writing_factcheck | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |
| writing_outline | `deepseek-v4-flash` | deepseek/deepseek-v4-flash | deepseek |

#### `writing-premium` — 10 roles
| Role | Key | Model | Lab |
|------|-----|-------|-----|
| primary | `gemini-pro` | anthropic/claude-sonnet-5 | anthropic |
| synthesis | `glm-5.2` | z-ai/glm-5.2 | zhipu |
| deep_read | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| fusion | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| meta_evaluator | `qwen3.7-max` | qwen/qwen3.7-max | qwen |
| scoring | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| stress_testing | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| verifier | `qwen3-max-thinking` | qwen/qwen3-max-thinking | qwen |
| writing_assemble | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
| writing_factcheck | `deepseek-v4-pro` | deepseek/deepseek-v4-pro | deepseek |
| writing_outline | `claude-sonnet` | anthropic/claude-sonnet-5 | anthropic |
