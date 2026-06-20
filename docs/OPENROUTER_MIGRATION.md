# Migrating from Direct API to OpenRouter

## Why Migrate?

| Benefit | Description |
|---------|-------------|
| **Simplified billing** | Single invoice instead of 7 different providers |
| **Single API key** | One environment variable instead of seven |
| **346+ models** | Access to models you don't currently have keys for |
| **Potentially lower prices** | OpenRouter negotiates bulk rates (e.g., DeepSeek V3 is 26% cheaper) |
| **Built-in fallbacks** | Automatic routing if a model is unavailable |
| **Cross-ecosystem diversity** | Maintain epistemic diversity without managing multiple keys |

---

## Migration Steps

### Step 1: Get OpenRouter API Key

1. Visit https://openrouter.ai/
2. Sign up for an account
3. Go to https://openrouter.ai/keys
4. Create a new API key
5. Copy the key (starts with `sk-or-v1-...`)

### Step 2: Update `.env` File

Add the OpenRouter API key to your `.env` file:

```bash
# Add this line:
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Optional: Comment out individual provider keys if you want to switch completely
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# GOOGLE_API_KEY=
# DEEPSEEK_API_KEY=
# DASHSCOPE_API_KEY=
# MOONSHOT_API_KEY=
# ZHIPUAI_API_KEY=
# MISTRAL_API_KEY=
# XAI_API_KEY=
# PERPLEXITY_API_KEY=
```

**Note:** You can keep both OpenRouter AND individual provider keys active. This allows you to:
- Use OpenRouter presets (`or-*`) for most runs
- Use direct API presets (`max-quality`, `cost-efficient`, etc.) when needed
- Mix models from both in custom routing

### Step 3: Update Your Commands

```bash
# Old (direct API):
python main.py --problem "What are the implications of quantum computing?" --preset balanced

# New (OpenRouter):
python main.py --problem "What are the implications of quantum computing?" --preset or-balanced
```

### Step 4: Verify It Works

```bash
# List all available presets (should show OpenRouter presets at the top)
python main.py --list-presets

# List available models (should show 'openrouter' group)
python main.py --list-models

# Test with cheapest preset:
python main.py --problem "What is 2+2?" --preset or-ultra-budget

# Test recommended preset:
python main.py --problem "How should we approach our Q4 strategy?" --preset or-balanced
```

---

## Model ID Mapping

OpenRouter models use the `-or` suffix to distinguish them from direct API models. This allows both to coexist.

| Direct API ID | OpenRouter ID | OpenRouter Model Path | Pricing (Input/Output per 1M) |
|---------------|---------------|----------------------|-------------------------------|
| `claude-opus` | `claude-opus-or` | `anthropic/claude-opus-4.6` | $5.00 / $25.00 |
| `claude-sonnet` | `claude-sonnet-or` | `anthropic/claude-sonnet-4.6` | $3.00 / $15.00 |
| `claude-haiku` | `claude-haiku-or` | `anthropic/claude-haiku-4.5` | $1.00 / $5.00 |
| `gpt-5` | `gpt-5-or` | `openai/gpt-5` | $1.25 / $10.00 |
| `gpt-5-mini` | `gpt-5-mini-or` | `openai/gpt-5-mini` | $0.75 / $4.50 |
| `gpt-5-pro` | `gpt-5-pro-or` | `openai/gpt-5-pro` | $15.00 / $120.00 |
| `gpt-4o` | `gpt-4o-or` | `openai/gpt-4o` | $2.50 / $10.00 |
| `o3` | `o3-or` | `openai/o3` | $2.00 / $8.00 |
| `o3-mini` | `o3-mini-or` | `openai/o3-mini` | $1.10 / $4.40 |
| `gemini-pro` | `gemini-pro-or` | `google/gemini-2.5-pro` | $1.25 / $10.00 |
| `gemini-flash` | `gemini-flash-or` | `google/gemini-2.5-flash` | $0.30 / $2.50 |
| `grok-4` | `grok-4-or` | `x-ai/grok-4` | $3.00 / $15.00 |
| `grok-3` | `grok-3-or` | `x-ai/grok-3` | $3.00 / $15.00 |
| `grok-3-mini` | `grok-3-mini-or` | `x-ai/grok-3-mini` | $0.30 / $1.50 |
| `sonar-pro` | `sonar-pro-or` | `perplexity/sonar-pro` | $3.00 / $15.00 |
| `sonar` | `sonar-or` | `perplexity/sonar` | $1.00 / $1.00 |
| `sonar-deep-research` | `sonar-deep-research-or` | `perplexity/sonar-deep-research` | $2.00 / $8.00 |
| `mistral-large-3` | `mistral-large-3-or` | `mistralai/mistral-large-2411` | $2.00 / $6.00 |
| `ministral-8b` | `ministral-8b-or` | `mistralai/ministral-8b` | Free tier |
| `ministral-3b` | `ministral-3b-or` | `mistralai/ministral-3b` | Free tier |
| `deepseek-v3` | `deepseek-v3-or` | `deepseek/deepseek-chat-v3-0324` | $0.20 / $0.77 |
| `deepseek-r1` | `deepseek-r1-or` | `deepseek/deepseek-r1-0528` | $0.50 / $2.15 |
| `qwen3-max` | `qwen3-max-or` | `qwen/qwen3-max` | $0.78 / $3.90 |
| `qwen3-plus` | `qwen3-plus-or` | `qwen/qwen-plus` | $0.26 / $0.78 |
| `qwen3-turbo` | `qwen3-turbo-or` | `qwen/qwen-turbo` | $0.03 / $0.13 |
| `kimi-k2` | `kimi-k2-or` | `moonshotai/kimi-k2` | $0.57 / $2.30 |
| `kimi-k2-5` | `kimi-k2-5-or` | `moonshotai/kimi-k2.5` | $0.38 / $1.72 |
| `glm-5` | `glm-5-or` | `z-ai/glm-5` | $0.72 / $2.30 |
| `glm-4-plus` | `glm-4-plus-or` | `z-ai/glm-4-plus` | Free tier |
| `glm-4-air` | `glm-4-air-or` | `z-ai/glm-4-air` | Free tier |

**Key Pricing Differences:**
- DeepSeek V3: **26% cheaper** on OpenRouter ($0.20 vs $0.27 input)
- All other models: Similar pricing to direct API
- Some models (Ministral, GLM-4) have free tiers on OpenRouter

---

## Preset Comparison

### Available OpenRouter Presets

| Preset | Primary Model | Cost/Run | Ecosystems | Best For |
|--------|--------------|----------|------------|----------|
| `or-ultra-budget` | deepseek-v3-or | ~$0.018 | 3 (DeepSeek, Qwen, GLM) | Experimentation, high volume |
| `or-budget-plus` | deepseek-v3-or | ~$0.022 | 5 (+ Gemini, Kimi) | Everyday budget use |
| `or-balanced` ⭐ | claude-sonnet-or | ~$0.062 | 6 (+ xAI/Grok) | **Recommended default** |
| `or-quality` | claude-opus-or | ~$0.174 | 6 (+ Perplexity) | Important decisions |
| `or-max-quality` | claude-opus-or | ~$0.299 | 6 (+ GPT-5 Pro) | High-stakes decisions |

### Direct API vs OpenRouter Cost Comparison

| Preset Type | Direct API Cost | OpenRouter Cost | Savings |
|-------------|----------------|-----------------|---------|
| Budget | ~$0.020 | ~$0.018 | 10% |
| Balanced | ~$0.120 | ~$0.062 | **48%** |
| Quality | ~$0.170 | ~$0.174 | Similar |

**Why the savings on balanced preset?**
- OpenRouter has better rates on DeepSeek V3 (26% cheaper)
- Single API key means no duplicate minimum charges
- OpenRouter's routing optimizes for cost when models are equivalent

---

## Can I Use Both?

**Yes!** The system fully supports using both OpenRouter and direct API simultaneously:

### Mixed Usage Examples

**1. Different presets for different needs:**
```bash
# Quick analysis - use OpenRouter budget
python main.py --problem "Summarize this article" --preset or-budget-plus

# Critical decision - use direct API max quality
python main.py --problem "Should we acquire this startup?" --preset max-quality
```

**2. Custom routing mixing both:**
```bash
python main.py --problem "..." --routing '{
  "classification": "gemini-flash-or",
  "decomposition": "claude-sonnet",
  "constructive": "kimi-k2-5-or",
  "scoring": "sonar-pro",
  "synthesis": "glm-5-or"
}'
```

**3. Fallback strategy:**
- If OpenRouter is down, direct API presets still work
- If a specific provider key is missing, that model won't be used
- Graceful degradation at every level

---

## Testing Your Migration

### Quick Tests

```bash
# 1. Verify OpenRouter models are registered
python main.py --list-models | grep -A 30 "openrouter"

# Should show 30+ models like:
# openrouter:
#   claude-haiku-or
#   claude-opus-or
#   claude-sonnet-or
#   ...

# 2. Verify OpenRouter presets are available
python main.py --list-presets | grep "or-"

# Should show:
# or-ultra-budget
# or-budget-plus
# or-balanced
# or-quality
# or-max-quality

# 3. Test cheapest preset
python main.py --problem "Explain what a neural network is in 2 sentences" --preset or-ultra-budget

# Should complete successfully with valid JSON output

# 4. Test recommended preset
python main.py --problem "What are the pros and cons of remote work?" --preset or-balanced

# Should use 6 different ecosystems
```

### Validation Checklist

- [ ] `OPENROUTER_API_KEY` is set in `.env`
- [ ] `python main.py --list-models` shows `openrouter` group
- [ ] `python main.py --list-presets` shows `or-*` presets
- [ ] `or-ultra-budget` preset completes successfully
- [ ] `or-balanced` preset completes successfully
- [ ] Output JSON contains expected structure (solution, insights, blueprint)
- [ ] Phase models show diversity (different ecosystems used)
- [ ] Costs match estimates (±20%)

---

## Troubleshooting

### "API key for 'xyz-or' is not set"

**Problem:** `OPENROUTER_API_KEY` not found in environment

**Solution:**
```bash
# Check if key is set
grep OPENROUTER_API_KEY .env

# Should show: OPENROUTER_API_KEY=sk-or-v1-...

# If missing, add it to .env file
echo 'OPENROUTER_API_KEY=sk-or-v1-your-key' >> .env
```

### "Unknown model ID: 'xyz-or'"

**Problem:** OpenRouter models not in registry

**Solution:**
- Ensure you're using the latest code (presets_openrouter.py exists)
- Check that llm.py contains the OPENROUTER section in _REGISTRY
- Restart Python/process to reload modules

### "Provider failed after 3 retries"

**Problem:** OpenRouter API request failing

**Possible causes:**
1. Invalid API key - verify at https://openrouter.ai/activity
2. Rate limiting - check OpenRouter dashboard for limits
3. Model unavailable - try different preset or model

**Solution:**
```bash
# Test with different model
python main.py --problem "..." --preset or-budget-plus

# Check OpenRouter status
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/models
```

### "JSON parsing failed"

**Problem:** Model output not valid JSON

**Solution:**
- Some models have different JSON output quality
- Try `--sequential` flag to avoid parallel parsing issues
- Use `--preset or-balanced` (tested for JSON reliability)

---

## Reverting Back

If you need to revert to direct API only:

```bash
# 1. Comment out or remove OPENROUTER_API_KEY from .env
# OPENROUTER_API_KEY=sk-or-v1-...

# 2. Uncomment your individual provider keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
# etc.

# 3. Use direct API presets instead of or-* presets
python main.py --problem "..." --preset balanced  # Instead of or-balanced
```

**Note:** OpenRouter models (`*-or`) will still be in the registry but will fail gracefully if `OPENROUTER_API_KEY` is not set. They won't interfere with direct API usage.

---

## Next Steps

After successful migration:

1. **Monitor costs** - Check https://openrouter.ai/activity for usage
2. **Experiment with presets** - Try all 5 OpenRouter presets
3. **Custom routing** - Create your own model combinations
4. **Provide feedback** - Report any issues or suggestions

For detailed pricing analysis and model recommendations, see:
- `openrouter_final_recommendations.md` - Comprehensive analysis
- `openrouter_models_formatted.txt` - Full model list with pricing

---

## FAQ

**Q: Will OpenRouter always be cheaper?**  
A: Not always. OpenRouter negotiates bulk rates which can change. Currently DeepSeek V3 is 26% cheaper. Other models are similar to direct API pricing.

**Q: Can I use OpenRouter for only some models?**  
A: Yes! Mix `-or` models with direct API models in custom routing.

**Q: What if OpenRouter goes down?**  
A: Direct API presets continue to work. You can also set up fallback routing.

**Q: Is there rate limiting on OpenRouter?**  
A: OpenRouter has rate limits per API key. Check your dashboard for limits. Generally higher than individual provider limits.

**Q: Do all models work the same on OpenRouter?**  
A: Functionally yes. Some models may have slightly different latency (OpenRouter adds ~10-50ms proxy overhead). JSON output quality should be identical.

**Q: Can I self-host OpenRouter?**  
A: No, OpenRouter is a managed service. For self-hosting, use Ollama or vLLM presets.

---

**Migration completed!** 🎉

You now have access to 346+ models through a single API key while maintaining full backward compatibility with direct API usage.
