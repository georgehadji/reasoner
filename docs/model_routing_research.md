# Deep Research: Optimal Model Routing per Phase per Preset

**Generated:** 2026-04-16
**Methodology:** Capability-based scoring across 7 dimensions (Reasoning, Instruction-Following, Creativity, Context, Efficiency, Factuality, Adversarialism). Cost-adjusted for Budget vs Premium tiers.

## Model Capability Matrix

| Model | Reasoning | IF | Creativity | Context | Efficiency | Factuality | Adversarial | Cost $/Mtok |
|-------|-----------|----|------------|---------|------------|------------|-------------|-------------|
| elephant-alpha       |  6.0 |  6.0 |  6.0 |  8.0 | 10.0 |  5.0 |  5.0 | $  0.000 |
| qwen3-turbo          |  6.0 |  7.0 |  6.0 |  6.0 | 10.0 |  6.0 |  6.0 | $  0.163 |
| glm-4-long           |  6.5 |  6.0 |  5.0 |  7.0 | 10.0 |  5.0 |  5.0 | $  0.200 |
| ministral-3b         |  6.0 |  7.0 |  5.0 |  5.0 | 10.0 |  5.0 |  5.0 | $  0.200 |
| ministral-8b         |  6.5 |  7.0 |  6.0 |  6.0 |  9.0 |  6.0 |  6.0 | $  0.300 |
| mimo-v2-flash        |  6.0 |  6.0 |  6.0 |  8.0 | 10.0 |  5.0 |  5.0 | $  0.380 |
| gemma-4-26b          |  6.5 |  7.0 |  6.0 |  8.0 | 10.0 |  6.0 |  6.0 | $  0.470 |
| gemma-4-31b          |  7.0 |  7.0 |  7.0 |  8.0 |  9.0 |  7.0 |  7.0 | $  0.510 |
| deepseek-v3          |  8.0 |  7.0 |  7.0 |  7.0 | 10.0 |  7.0 |  8.0 | $  0.640 |
| gpt-4o-mini          |  7.0 |  9.0 |  6.0 |  7.0 |  9.0 |  7.0 |  6.0 | $  0.750 |
| grok-3-mini          |  7.0 |  8.0 |  6.0 |  7.0 |  9.0 |  7.0 |  6.0 | $  0.800 |
| glm-4-air            |  7.0 |  7.0 |  6.0 |  7.0 |  9.0 |  6.0 |  6.0 | $  0.980 |
| qwen3-coder          |  7.0 |  8.0 |  5.0 |  7.0 |  9.0 |  6.0 |  5.0 | $  1.000 |
| arcee-trinity-large-thinking |  7.0 |  7.0 |  6.0 |  8.0 |  9.0 |  6.0 |  6.0 | $  1.070 |
| minimax-m2-5         |  7.0 |  7.0 |  7.0 |  8.0 |  9.0 |  6.0 |  6.0 | $  1.108 |
| minimax-m2           |  7.0 |  7.0 |  7.0 | 10.0 |  8.0 |  6.0 |  6.0 | $  1.300 |
| arcee-coder-large    |  7.0 |  8.0 |  5.0 |  5.0 |  9.0 |  6.0 |  5.0 | $  1.300 |
| codestral            |  7.0 |  8.0 |  5.0 |  6.0 |  8.0 |  6.0 |  5.0 | $  1.500 |
| minimax-m2-7         |  7.5 |  7.0 |  7.0 |  8.0 |  9.0 |  7.0 |  7.0 | $  1.500 |
| qwen3-plus           |  7.5 |  8.0 |  7.0 | 10.0 |  9.0 |  7.0 |  7.0 | $  1.820 |
| arcee-virtuoso-large |  7.5 |  7.0 |  7.0 |  7.0 |  8.0 |  7.0 |  7.0 | $  1.950 |
| mistral-large-3      |  8.0 |  8.0 |  8.0 |  8.0 |  8.0 |  7.0 |  8.0 | $  2.000 |
| sonar                |  7.0 |  7.0 |  6.0 |  7.0 |  7.0 |  9.0 |  6.0 | $  2.000 |
| kimi-k2-5            |  8.5 |  8.0 |  9.0 |  8.0 |  9.0 |  7.0 |  8.0 | $  2.103 |
| qwen3-max            |  8.0 |  8.0 |  8.0 | 10.0 |  9.0 |  7.0 |  8.0 | $  2.275 |
| glm-4-airx           |  7.5 |  7.0 |  7.0 |  8.0 |  7.0 |  7.0 |  7.0 | $  2.290 |
| mistral-medium       |  7.5 |  7.0 |  7.0 |  7.0 |  8.0 |  6.0 |  7.0 | $  2.400 |
| mimo-v2-omni         |  6.5 |  7.0 |  6.0 |  8.0 |  9.0 |  6.0 |  6.0 | $  2.400 |
| deepseek-r1          |  9.5 |  7.0 |  7.0 |  7.0 |  8.0 |  8.0 |  9.0 | $  2.650 |
| gemini-flash         |  7.0 |  8.0 |  7.0 | 10.0 |  9.0 |  7.0 |  7.0 | $  2.800 |
| glm-4-plus           |  7.5 |  7.0 |  6.0 |  7.0 |  8.0 |  6.0 |  6.0 | $  2.800 |
| kimi-k2              |  8.0 |  8.0 |  9.0 |  7.0 |  9.0 |  7.0 |  8.0 | $  2.870 |
| glm-5                |  8.0 |  7.0 |  7.0 |  6.0 |  8.0 |  7.0 |  7.0 | $  3.020 |
| kimi-k2-thinking     |  9.0 |  7.0 |  8.0 |  8.0 |  8.0 |  7.0 |  8.0 | $  3.100 |
| mimo-v2-pro          |  7.0 |  7.0 |  7.0 | 10.0 |  8.0 |  6.0 |  6.0 | $  4.000 |
| glm-5.1              |  8.5 |  8.0 |  7.0 |  8.0 |  7.0 |  7.0 |  7.0 | $  4.100 |
| arcee-maestro-reasoning |  8.0 |  7.0 |  6.0 |  7.0 |  7.0 |  7.0 |  7.0 | $  4.200 |
| gpt-5-mini           |  7.0 |  9.0 |  7.0 |  8.0 |  8.0 |  8.0 |  7.0 | $  5.250 |
| o3-mini              |  9.0 |  9.0 |  6.0 |  7.0 |  7.0 |  8.0 |  7.0 | $  5.500 |
| claude-haiku         |  7.0 |  9.0 |  6.0 |  8.0 |  7.0 |  8.0 |  7.0 | $  6.000 |
| grok-4.20            |  9.0 |  8.0 |  8.0 | 10.0 |  7.0 |  8.0 |  9.0 | $  8.000 |
| o3                   | 10.0 |  9.0 |  7.0 |  8.0 |  4.0 |  9.0 |  8.0 | $ 10.000 |
| sonar-deep-research  |  9.0 |  8.0 |  7.0 |  7.0 |  4.0 | 10.0 |  7.0 | $ 10.000 |
| sonar-reasoning-pro  |  8.5 |  8.0 |  6.0 |  7.0 |  5.0 | 10.0 |  7.0 | $ 10.000 |
| gemini-pro           |  9.0 |  8.0 |  8.0 | 10.0 |  5.0 |  8.0 |  8.0 | $ 11.250 |
| gpt-4o               |  8.0 |  9.0 |  8.0 |  8.0 |  5.0 |  8.0 |  8.0 | $ 12.500 |
| gpt-5                | 10.0 | 10.0 |  9.0 | 10.0 |  4.0 |  9.0 |  9.0 | $ 17.500 |
| claude-sonnet        |  9.0 | 10.0 |  8.0 | 10.0 |  5.0 |  9.0 |  9.0 | $ 18.000 |
| grok-4               |  9.0 |  8.0 |  8.0 |  9.0 |  5.0 |  8.0 |  9.0 | $ 18.000 |
| grok-3               |  8.5 |  8.0 |  8.0 |  7.0 |  5.0 |  7.0 |  8.0 | $ 18.000 |
| sonar-pro            |  8.0 |  8.0 |  6.0 |  8.0 |  5.0 | 10.0 |  7.0 | $ 18.000 |
| claude-opus          | 10.0 | 10.0 |  8.0 | 10.0 |  3.0 | 10.0 | 10.0 | $ 30.000 |

## MULTI PERSPECTIVE BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## MULTI PERSPECTIVE PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## ITERATIVE BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## ITERATIVE PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## DEBATE BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## DEBATE PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## SCIENTIFIC BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## SCIENTIFIC PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## SOCRATIC BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## SOCRATIC PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## RESEARCH BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## RESEARCH PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## JURY BUDGET

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gemma-4-26b` | 8.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |
| 2 | `gpt-4o-mini` | 8.75 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `qwen3-turbo` | 8.70 | 131,072 | $0.163 | Ultra-cheap, good enough for this phase |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `qwen3-plus` | 7.94 | 1,000,000 | $1.820 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.93 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-4o-mini` | 8.56 | 128,000 | $0.750 | Excellent price/performance ratio |
| 2 | `deepseek-v3` | 8.50 | 163,840 | $0.640 | Excellent price/performance ratio |
| 3 | `gemma-4-26b` | 8.49 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.15 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.60 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## JURY PREMIUM

### Phase: `classification`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `kimi-k2-5` | 8.90 | 262,144 | $2.103 | Strong all-rounder |
| 2 | `grok-4.20` | 8.81 | 2,000,000 | $8.000 | Massive context + strong reasoning |
| 3 | `claude-sonnet` | 8.73 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `decomposition`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.97 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.95 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.71 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `minimalist`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-sonnet` | 9.16 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 2 | `gpt-5` | 9.07 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 3 | `grok-4.20` | 9.02 | 2,000,000 | $8.000 | Massive context + strong reasoning |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `stress_testing`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.26 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.77 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## PRE MORTEM BUDGET

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.03 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.84 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## PRE MORTEM PREMIUM

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.62 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-sonnet` | 9.33 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 3 | `claude-opus` | 9.25 | 1,000,000 | $30.000 | Best-in-class reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## BAYESIAN BUDGET

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.03 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.84 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## BAYESIAN PREMIUM

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.62 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-sonnet` | 9.33 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 3 | `claude-opus` | 9.25 | 1,000,000 | $30.000 | Best-in-class reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## DIALECTICAL BUDGET

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.03 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.84 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 7.96 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.72 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.24 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.87 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-31b` | 7.68 | 262,144 | $0.510 | Excellent price/performance ratio |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `gpt-4o-mini` | 7.92 | 128,000 | $0.750 | Excellent price/performance ratio |
| 3 | `mistral-large-3` | 7.76 | 262,144 | $2.000 | Best reasoning within budget constraints |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## DIALECTICAL PREMIUM

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.62 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-sonnet` | 9.33 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 3 | `claude-opus` | 9.25 | 1,000,000 | $30.000 | Best-in-class reasoning |

### Phase: `constructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.77 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.39 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.36 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `destructive`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.18 | 1,000,000 | $30.000 | Best-in-class reasoning | exceptional adversarial thinking |
| 2 | `gpt-5` | 9.87 | 1,050,000 | $17.500 | Best-in-class reasoning | exceptional adversarial thinking |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning | exceptional adversarial thinking |

### Phase: `scoring`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.29 | 1,000,000 | $30.000 | Best-in-class reasoning | fact-checking strength |
| 2 | `gpt-5` | 10.06 | 1,050,000 | $17.500 | Best-in-class reasoning | fact-checking strength |
| 3 | `claude-sonnet` | 9.89 | 1,000,000 | $18.000 | Massive context + strong reasoning | fact-checking strength |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## ANALOGICAL BUDGET

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.03 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.84 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.04 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.90 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `qwen3-plus` | 7.73 | 1,000,000 | $1.820 | Best reasoning within budget constraints |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## ANALOGICAL PREMIUM

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.62 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-sonnet` | 9.33 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 3 | `claude-opus` | 9.25 | 1,000,000 | $30.000 | Best-in-class reasoning |

### Phase: `systemic`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 10.16 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 10.10 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.74 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |

## DELPHI BUDGET

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.03 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.92 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gpt-4o-mini` | 7.84 | 128,000 | $0.750 | Excellent price/performance ratio |

### Phase: `expert`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `deepseek-v3` | 8.19 | 163,840 | $0.640 | Excellent price/performance ratio |
| 2 | `mistral-large-3` | 7.88 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `gemma-4-26b` | 7.84 | 262,144 | $0.470 | Ultra-cheap, good enough for this phase |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `qwen3-plus` | 8.19 | 1,000,000 | $1.820 | Best reasoning within budget constraints | 1M+ ctx ideal for synthesis |
| 2 | `mistral-large-3` | 7.89 | 262,144 | $2.000 | Best reasoning within budget constraints |
| 3 | `deepseek-v3` | 7.83 | 163,840 | $0.640 | Excellent price/performance ratio |

## DELPHI PREMIUM

### Phase: `prompt_enhancement`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.62 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-sonnet` | 9.33 | 1,000,000 | $18.000 | Massive context + strong reasoning |
| 3 | `claude-opus` | 9.25 | 1,000,000 | $30.000 | Best-in-class reasoning |

### Phase: `expert`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `gpt-5` | 9.76 | 1,050,000 | $17.500 | Best-in-class reasoning |
| 2 | `claude-opus` | 9.68 | 1,000,000 | $30.000 | Best-in-class reasoning |
| 3 | `claude-sonnet` | 9.50 | 1,000,000 | $18.000 | Massive context + strong reasoning |

### Phase: `synthesis`

| Rank | Model | Score | Context | Cost $/Mtok | Rationale |
|------|-------|-------|---------|-------------|-----------|
| 1 | `claude-opus` | 10.59 | 1,000,000 | $30.000 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 2 | `gpt-5` | 10.55 | 1,050,000 | $17.500 | Best-in-class reasoning | 1M+ ctx ideal for synthesis |
| 3 | `claude-sonnet` | 10.22 | 1,000,000 | $18.000 | Massive context + strong reasoning | 1M+ ctx ideal for synthesis |
