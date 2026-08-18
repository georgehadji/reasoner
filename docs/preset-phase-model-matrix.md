# Preset -> Phase -> Model Matrix

Generated from `domain/preset_registry.py` after the 2026-08-18 routing change.
`resolved` = the actually-served model (several aliases route cross-vendor, e.g.
`gemini-pro` -> Anthropic, `gemini-flash-lite` -> Qwen).

**Fallback** mirrors `ProviderRouter.call` precedence: explicit `fallback_routing[role]`
> `fallback_routing['primary']` (only when the role already uses the primary model)
> the primary model itself. Candidates resolving to the *same served model* as the
assigned one are dropped, so `none` means a failure on that role has nowhere to go.

Across all 50 presets: **76 of 495 role slots have no usable fallback.**


## `analogical-budget`

method `analogical` | tags: budget, creative, reasoning

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `analogical-premium`

method `analogical` | tags: premium, creative, reasoning

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `article-budget`

method `article` | tags: budget, writing, article

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | **none** |
| `article_critic` | `hy3` | CN | `tencent/hy3` | $0.132/$0.528 262K | `deepseek-v4-flash` |
| `article_humanize` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | `deepseek-v4-flash` |
| `article_revise` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | **none** |
| `article_sot_skeleton` | `gpt-4o-mini` | US | `openai/gpt-4o-mini` | $0.15/$0.6 128K | `deepseek-v4-flash` |
| `article_verifier` | `hy3` | CN | `tencent/hy3` | $0.132/$0.528 262K | `deepseek-v4-flash` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | **none** |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `deepseek-v4-flash` |
| `primary` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `deepseek-v4-flash` |
| `synthesis` | `qwen3.7-plus` | CN | `qwen/qwen3.7-plus` | $0.32/$1.28 1000K | `deepseek-v4-flash` |
| `writing_assemble` | `gpt-4o-mini` | US | `openai/gpt-4o-mini` | $0.15/$0.6 128K | `deepseek-v4-flash` |
| `writing_draft` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | `deepseek-v4-flash` |
| `writing_factcheck` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `deepseek-v4-flash` |

## `article-premium`

method `article` | tags: premium, writing, article

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `article_critic` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `claude-sonnet` |
| `article_humanize` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `article_revise` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `claude-sonnet` |
| `article_sot_skeleton` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `article_verifier` | `qwen3.7-max` | CN | `qwen/qwen3.7-max` | $1.48/$4.42 1000K | `claude-sonnet` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `claude-sonnet` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `claude-sonnet` |
| `primary` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `claude-sonnet` |
| `synthesis` | `qwen3.7-max` | CN | `qwen/qwen3.7-max` | $1.48/$4.42 1000K | `claude-sonnet` |
| `writing_assemble` | `gpt-4o-mini` | US | `openai/gpt-4o-mini` | $0.15/$0.6 128K | `claude-sonnet` |
| `writing_draft` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `writing_factcheck` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `claude-sonnet` |
| `writing_outline` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |

## `bayesian-budget`

method `bayesian` | tags: budget, analytical, probabilistic

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-haiku` | US | `anthropic/claude-haiku-4.5` | $1/$5 200K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `claude-haiku` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `claude-haiku` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `claude-haiku` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `claude-haiku` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `claude-haiku` |

## `bayesian-premium`

method `bayesian` | tags: premium, analytical, probabilistic

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `brainstorming-budget`

method `brainstorming` | tags: budget, creative

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-haiku` | US | `anthropic/claude-haiku-4.5` | $1/$5 200K | **none** |
| `brainstorm_cluster` | `google/gemma-2-9b-it` | US | `google/gemma-3-12b-it` | $0.05/$0.15 131K | `claude-haiku` |
| `brainstorm_develop` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `claude-haiku` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `claude-haiku` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `claude-haiku` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `claude-haiku` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `claude-haiku` |

## `brainstorming-premium`

method `brainstorming` | tags: premium, creative

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `brainstorm_cluster` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `brainstorm_develop` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `claude-sonnet` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `claude-sonnet` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `claude-sonnet` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `claude-sonnet` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `claude-sonnet` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `claude-sonnet` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `claude-sonnet` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `claude-sonnet` |

## `coding-budget`

method `coding` | tags: budget, coding, software-development

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `qwen3-coder-flash` | CN | `qwen/qwen3-coder-flash` | $0.195/$0.975 1000K | `codestral-2508` |
| `coding_assemble` | `laguna-xs-2.1` | US | `poolside/laguna-xs-2.1` | $0.06/$0.12 262K | `qwen3-coder-flash` |
| `coding_review` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `qwen3-coder-flash` |
| `coding_spec` | `qwen3-coder-flash` | CN | `qwen/qwen3-coder-flash` | $0.195/$0.975 1000K | `codestral-2508` |
| `coding_tests` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `qwen3-coder-flash` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `qwen3-coder-flash` |
| `meta_evaluator` | `qwen3.7-plus` | CN | `qwen/qwen3.7-plus` | $0.32/$1.28 1000K | `qwen3-coder-flash` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `qwen3-coder-flash` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `qwen3-coder-flash` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `qwen3-coder-flash` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `qwen3-coder-flash` |
| `verifier` | `qwen3.7-plus` | CN | `qwen/qwen3.7-plus` | $0.32/$1.28 1000K | `qwen3-coder-flash` |

Cascades (tried in order, quality-gated, bypass the table above):

- `coding_generate`: `qwen3-coder-flash`(CN) -> `kat-coder-pro-v2.5`(OTHER) -> `laguna-xs-2.1`(US) -> `kat-coder-air-v2.5`(OTHER) -> `codestral-2508`(EU) -> `grok-build-0.1`(US) -> `deepseek-v4-flash`(CN)
- `coding_review`: `deepseek-v4-flash`(CN) -> `kat-coder-pro-v2.5`(OTHER) -> `mimo-v2.5-pro`(CN) -> `codestral-2508`(EU) -> `gpt-5.1-codex-mini`(US)

## `coding-premium`

method `coding` | tags: premium, coding, software-development

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `coding_assemble` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-sonnet` |
| `coding_review` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-sonnet` |
| `coding_spec` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `coding_tests` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-sonnet` |
| `deep_read` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `claude-sonnet` |
| `meta_evaluator` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `claude-sonnet` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `claude-sonnet` |
| `scoring` | `qwen3.8-max` | CN | `qwen/qwen3.8-max` | $2/$6 1000K | `claude-sonnet` |
| `stress_testing` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `claude-sonnet` |
| `verifier` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `claude-sonnet` |

## `cove-budget`

method `cove` | tags: budget, verification, fact-checking

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `cove_answer` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `cove_revise` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `cove_verify` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `cove-premium`

method `cove` | tags: premium, verification, fact-checking

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `cove_answer` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `cove_revise` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-pro` |
| `cove_verify` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `cross-language-budget`

method `cross-language` | tags: budget, translation, multilingual

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `cross-language-premium`

method `cross-language` | tags: premium, translation, multilingual

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `gemini-pro-real` | US | `google/gemini-3.1-pro-preview` | $2/$12 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `verifier` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |

## `debate-budget`

method `debate` | tags: budget, argumentative, robust

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `grok-4.3` | US | `x-ai/grok-4.3` | $1.25/$2.5 1000K | **none** |
| `constructive` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `destructive` | `gpt-oss-120b` | US | `openai/gpt-oss-120b` | $0.03/$0.17 131K | `grok-4.3` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `grok-4.3` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `grok-4.3` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `grok-4.3` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `grok-4.3` |
| `systemic` | `grok-4.3` | US | `x-ai/grok-4.3` | $1.25/$2.5 1000K | **none** |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `grok-4.3` |

## `debate-premium`

method `debate` | tags: premium, argumentative, robust

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `constructive` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `destructive` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `systemic` | `gemini-pro-real` | US | `google/gemini-3.1-pro-preview` | $2/$12 1048K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `delphi-budget`

method `delphi` | tags: budget, collaborative, forecasting

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `delphi-premium`

method `delphi` | tags: premium, collaborative, forecasting

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `dialectical-budget`

method `dialectical` | tags: budget, argumentative, philosophical

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `dialectical-premium`

method `dialectical` | tags: premium, argumentative, philosophical

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `image-gen-budget`

method `image-gen` | tags: image-generation, creative, budget

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `grok-4.3` | US | `x-ai/grok-4.3` | $1.25/$2.5 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `image_generate` | `gemini-3.1-flash-lite-image` | US | `google/gemini-3.1-flash-lite-image` | $0.25/$1.5 65K | `grok-4.3` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `grok-4.3` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `grok-4.3` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `grok-4.3` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `grok-4.3` |

## `image-gen-premium`

method `image-gen` | tags: image-generation, creative, premium

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `image_generate` | `gemini-pro-image` | US | `google/gemini-3-pro-image` | $2/$12 131K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `iterative-critique-budget`

method `iterative-critique` | tags: budget, iterative, critique

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `grok-4.3` | US | `x-ai/grok-4.3` | $1.25/$2.5 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `meta_evaluator` | `mistral-small-2603` | EU | `mistralai/mistral-small-2603` | $0.15/$0.6 262K | `grok-4.3` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `grok-4.3` |
| `scoring` | `qwen3.6-flash` | CN | `qwen/qwen3.6-flash` | $0.188/$1.12 1000K | `grok-4.3` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `grok-4.3` |
| `synthesis` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | `grok-4.3` |
| `verifier` | `gemini-flash-lite-real` | US | `google/gemini-3.1-flash-lite` | $0.25/$1.5 1048K | `grok-4.3` |

## `iterative-critique-premium`

method `iterative-critique` | tags: premium, iterative, critique

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `claude-sonnet` |
| `fusion` | `mistral-large-3` | EU | `mistralai/mistral-large-2512` | $0.5/$1.5 262K | `claude-sonnet` |
| `meta_evaluator` | `kimi-k2-6` | CN | `moonshotai/kimi-k2.6` | $0.56/$2.36 262K | `claude-sonnet` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `claude-sonnet` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `claude-sonnet` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `claude-sonnet` |
| `synthesis` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `verifier` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `claude-sonnet` |

## `jury-budget`

method `jury` | tags: budget, governance, decision-making

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `jury-premium`

method `jury` | tags: premium, governance, decision-making

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `multi-perspective-budget`

method `multi-perspective` | tags: budget, balanced

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `grok-4.3` | US | `x-ai/grok-4.3` | $1.25/$2.5 1000K | **none** |
| `constructive` | `deepseek-v3` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `destructive` | `hermes-4-70b` | US | `nousresearch/hermes-4-70b` | $0.13/$0.4 131K | `grok-4.3` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `grok-4.3` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `grok-4.3` |
| `minimalist` | `ministral-8b` | EU | `mistralai/mistral-small-3.2-24b-instruct` | $0.0938/$0.25 256K | `grok-4.3` |
| `perspective_analysis` | `qwen3.6-flash` | CN | `qwen/qwen3.6-flash` | $0.188/$1.12 1000K | `grok-4.3` |
| `perspective_cot` | `mimo-v2.5` | CN | `xiaomi/mimo-v2.5` | $0.14/$0.28 1050K | `grok-4.3` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `grok-4.3` |
| `scoring` | `hy3` | CN | `tencent/hy3` | $0.132/$0.528 262K | `grok-4.3` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `grok-4.3` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `grok-4.3` |
| `systemic` | `hy3` | CN | `tencent/hy3` | $0.132/$0.528 262K | `grok-4.3` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `grok-4.3` |

## `multi-perspective-premium`

method `multi-perspective` | tags: premium, balanced, multilingual

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `constructive` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `destructive` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `minimalist` | `mistral-large-3` | EU | `mistralai/mistral-large-2512` | $0.5/$1.5 262K | `gemini-pro` |
| `perspective_analysis` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `perspective_cot` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `systemic` | `qwen3.7-max` | CN | `qwen/qwen3.7-max` | $1.48/$4.42 1000K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `multi-perspective-ultra-budget`

method `multi-perspective` | tags: budget, creative, fast

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `constructive` | `stepfun-3.7-flash` | CN | `stepfun/step-3.7-flash` | $0.2/$1.15 262K | `gemini-flash-lite` |
| `destructive` | `ling-2.6-flash-free` | CN | `inclusionai/ling-2.6-flash` | $0.01/$0.03 262K | `gemini-flash-lite` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `minimalist` | `ministral-8b` | EU | `mistralai/mistral-small-3.2-24b-instruct` | $0.0938/$0.25 256K | `gemini-flash-lite` |
| `perspective_analysis` | `qwen3.6-flash` | CN | `qwen/qwen3.6-flash` | $0.188/$1.12 1000K | `gemini-flash-lite` |
| `perspective_cot` | `qwen3.5-flash` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `systemic` | `gpt-oss-20b` | US | `openai/gpt-oss-20b` | $0.03/$0.13 131K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `nvidia-nemotron-test`

method `multi-perspective` | tags: experimental, nvidia

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `nvidia-nemotron-super` | US | `nvidia/nemotron-3-super-120b-a12b` | $0.085/$0.4 1000K | **none** |
| `perspective_analysis` | `nvidia-nemotron-super` | US | `nvidia/nemotron-3-super-120b-a12b` | $0.085/$0.4 1000K | **none** |
| `perspective_cot` | `nvidia-nemotron-super` | US | `nvidia/nemotron-3-super-120b-a12b` | $0.085/$0.4 1000K | **none** |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `nvidia-nemotron-super` |
| `synthesis` | `nvidia-nemotron-super` | US | `nvidia/nemotron-3-super-120b-a12b` | $0.085/$0.4 1000K | **none** |

## `pot-budget`

method `pot` | tags: budget, programming, code-generation

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `pot-premium`

method `pot` | tags: premium, programming, code-generation

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `pre-mortem-budget`

method `pre_mortem` | tags: budget, risk-assessment, strategic

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `pre-mortem-premium`

method `pre_mortem` | tags: premium, risk-assessment, strategic

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `research-budget`

method `research` | tags: budget, research, web-search

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-haiku` | US | `anthropic/claude-haiku-4.5` | $1/$5 200K | **none** |
| `deep_read` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `claude-haiku` |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `claude-haiku` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `claude-haiku` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `claude-haiku` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `claude-haiku` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `claude-haiku` |

## `research-premium`

method `research` | tags: premium, research, web-search

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `sonar-reasoning-pro` | US | `perplexity/sonar-reasoning-pro` | $2/$8 128K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `sonar-deep-research` | US | `perplexity/sonar-deep-research` | $2/$8 128K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `scientific-budget`

method `scientific` | tags: budget, scientific, structured

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `claude-haiku` | US | `anthropic/claude-haiku-4.5` | $1/$5 200K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `claude-haiku` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `claude-haiku` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `claude-haiku` |
| `scoring` | `qwen3.6-flash` | CN | `qwen/qwen3.6-flash` | $0.188/$1.12 1000K | `claude-haiku` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `claude-haiku` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `claude-haiku` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `claude-haiku` |

## `scientific-premium`

method `scientific` | tags: premium, scientific, structured

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `self-discover-budget`

method `self_discover` | tags: budget, reasoning, self-improvement

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `sd_adapt` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `sd_implement` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `sd_select` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `self-discover-premium`

method `self_discover` | tags: premium, reasoning, self-improvement

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `sd_adapt` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `sd_implement` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `sd_select` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `socratic-budget`

method `socratic` | tags: budget, educational, inquisitive

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `socratic-premium`

method `socratic` | tags: premium, educational, inquisitive

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `sot-budget`

method `sot` | tags: budget, structured-thinking, outlining

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `sot-premium`

method `sot` | tags: premium, structured-thinking, outlining

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `subagent-budget`

method `subagent` | tags: budget, multi-agent, delegation

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-plus` | CN | `qwen/qwen3.7-plus` | $0.32/$1.28 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `subagent_critique_bias` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `subagent_critique_counter` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `subagent_critique_evidence` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `subagent_critique_logic` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `subagent_decomposition` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `verifier` | `qwen3.7-plus` | CN | `qwen/qwen3.7-plus` | $0.32/$1.28 1000K | `gemini-flash-lite` |

## `subagent-premium`

method `subagent` | tags: premium, multi-agent, delegation

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `qwen3.7-max` | CN | `qwen/qwen3.7-max` | $1.48/$4.42 1000K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `subagent_critique_bias` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `subagent_critique_counter` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `subagent_critique_evidence` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `subagent_critique_logic` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `subagent_decomposition` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `verifier` | `qwen3-max-thinking` | CN | `qwen/qwen3-max-thinking` | $0.78/$3.9 262K | `gemini-pro` |

## `tot-budget`

method `tot` | tags: budget, problem-solving, exploration

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `meta_evaluator` | `qwen3.7-flash` | CN | `qwen/qwen3.7-flash` | $0.03/$0.13 1000K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `scoring` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `stress_testing` | `ring-2.6-1t` | CN | `inclusionai/ring-2.6-1t` | $0.075/$0.625 262K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `tot_backtrack` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `tot_decompose` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `tot_evaluate` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `verifier` | `gemini-2.5-flash-lite` | US | `google/gemini-2.5-flash-lite` | $0.1/$0.4 1048K | `gemini-flash-lite` |

## `tot-premium`

method `tot` | tags: premium, problem-solving, exploration

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `deep_read` | `gemini-3.7-flash` | US | `google/gemini-3.7-flash` | $0.375/$1.88 1048K | `gemini-pro` |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `meta_evaluator` | `minimax-m3` | CN | `minimax/minimax-m3` | $0.3/$1.2 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `scoring` | `glm-5.2` | CN | `z-ai/glm-5.2` | $1.19/$3.74 1048K | `gemini-pro` |
| `stress_testing` | `grok-4.6` | US | `x-ai/grok-4.6` | $2/$6 500K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `tot_backtrack` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-pro` |
| `tot_decompose` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `tot_evaluate` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-pro` |
| `verifier` | `grok-4.20` | US | `x-ai/grok-4.20` | $1.25/$2.5 2000K | `gemini-pro` |

## `writing-budget`

method `writing` | tags: budget, writing, content-creation

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-flash-lite` | CN | `qwen/qwen3.5-flash-02-23` | $0.065/$0.26 1000K | **none** |
| `fusion` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `post_synthesis_verify` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `primary` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-flash-lite` |
| `writing_assemble` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |
| `writing_factcheck` | `sonar` | US | `perplexity/sonar` | $1/$1 127K | `gemini-flash-lite` |
| `writing_outline` | `deepseek-v4-flash` | CN | `deepseek/deepseek-v4-flash` | $0.0798/$0.16 1048K | `gemini-flash-lite` |

## `writing-premium`

method `writing` | tags: premium, writing, content-creation

| role | model | bloc | resolved | price/ctx | fallback |
|---|---|---|---|---|---|
| `primary_id` | `gemini-pro` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `fusion` | `deepseek-v4-pro` | CN | `deepseek/deepseek-v4-pro` | $0.66/$1.98 1048K | `gemini-pro` |
| `post_synthesis_verify` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `primary` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `synthesis` | `gpt-5.6-luna` | US | `openai/gpt-5.6-luna` | $0.2/$1.2 1050K | `gemini-pro` |
| `writing_assemble` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
| `writing_factcheck` | `sonar-pro` | US | `perplexity/sonar-pro` | $3/$15 200K | `gemini-pro` |
| `writing_outline` | `claude-sonnet` | US | `anthropic/claude-sonnet-5` | $2/$10 1000K | **none** |
