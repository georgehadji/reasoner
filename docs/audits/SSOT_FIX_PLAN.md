# Plan: Fix SSOT Violations in Reasoner

## Context

An audit identified hardcoded model paths, inline temperature/token literals, and configuration dicts that bypass the project's established single-source-of-truth systems:
- **Model aliases**: `src/reasoner/core/constants_models.py` + `src/reasoner/infrastructure/llm/registry.py`
- **Temperature canon**: `src/reasoner/core/temperatures.py`
- **Token budget canon**: `PHASE_TOKEN_BUDGETS` in `src/reasoner/core/constants_limits.py`
- **Runtime config**: `src/reasoner/core/settings.py`

The highest-severity violations use raw OpenRouter paths (`"google/gemini-2.0-flash-001"`, `"anthropic/claude-3-haiku"`) that **are not in the registry whitelist** — these can cause runtime failures when those paths hit `build_provider()`. Lower-severity violations create drift risks where model upgrades or budget adjustments in the canonical source don't propagate.

---

## Ordered Changes

### 1. Add `MODEL_CLAUDE_HAIKU` constant

**File:** `src/reasoner/core/constants_models.py`

Add after line 5 (near other `MODEL_CLAUDE_*` entries):
```python
MODEL_CLAUDE_HAIKU: str = "claude-haiku"
```
This alias already has a registry entry (`"claude-haiku"` → `anthropic/claude-haiku-4.5`). The constant is needed before fixing downstream uses.

---

### 2. Fix `neuro/config.py` fallback model paths [CRITICAL]

**File:** `src/reasoner/neuro/config.py` — `_apply_defaults()` function, ~lines 293 and 299

**Problem:** `"google/gemini-2.0-flash-001"` and `"anthropic/claude-3-haiku"` are raw OpenRouter paths that are NOT in the registry whitelist. Passing them to `build_provider()` raises "Unknown model ID" at runtime.

**Fix:** Replace raw paths with registry aliases. Add imports at top of file:
```python
from reasoner.core.constants_models import MODEL_GEMINI_FLASH, MODEL_CLAUDE_HAIKU
```

Then replace:
- `"google/gemini-2.0-flash-001"` → `MODEL_GEMINI_FLASH`
- `"anthropic/claude-3-haiku"` → `MODEL_CLAUDE_HAIKU`

---

### 3. Fix `QUALITY_JUDGE_MODELS["premium"]` in constants_limits [HIGH]

**File:** `src/reasoner/core/constants_limits.py` — `QUALITY_JUDGE_MODELS` dict, line 146

**Problem:** `"google/gemini-2.0-flash-001"` is a raw OpenRouter path not in the registry whitelist. Same runtime failure risk as above.

**Fix:** Update the dict to use the existing `MODEL_GEMINI_FLASH` alias (already imported at the top of the file via `MODEL_GEMINI_FLASH_LITE` — `MODEL_GEMINI_FLASH` is already in `constants_models.py`):
```python
from reasoner.core.constants_models import MODEL_GEMINI_FLASH, MODEL_GEMINI_FLASH_LITE

QUALITY_JUDGE_MODELS: dict[str, str] = {
    "budget":  MODEL_GEMINI_FLASH_LITE,  # was: "gemini-flash-lite"
    "premium": MODEL_GEMINI_FLASH,        # was: "google/gemini-2.0-flash-001"
    "default": MODEL_GEMINI_FLASH_LITE,  # was: "gemini-flash-lite"
}
```

---

### 4. Fix `settings.py` NEURO_REASONING_MODEL default [MEDIUM]

**File:** `src/reasoner/core/settings.py` — line 136

**Problem:** Default value `"openai/gpt-4o-mini"` is a raw OpenRouter path. `MODEL_GPT4O_MINI = "gpt-4o-mini"` already exists in `constants_models.py` and is the correct alias.

**Fix:**
```python
from reasoner.core.constants_models import MODEL_GPT4O_MINI
# ...
NEURO_REASONING_MODEL: str = os.getenv("NEURO_REASONING_MODEL", MODEL_GPT4O_MINI)
```

---

### 5. Add `"fusion"` to `PHASE_TEMPERATURES` [MEDIUM]

**File:** `src/reasoner/core/temperatures.py`

**Problem:** `"fusion"` key is missing from `PHASE_TEMPERATURES`. `pipeline.py:106` uses `PHASE_TEMPERATURES.get("fusion", 0.1)` — the `0.1` fallback is the only definition of this value.

**Fix:** Add to `PHASE_TEMPERATURES` dict (fusion combines classification + decomposition, which use 0.3–0.4; 0.2 is appropriate for the combined structured-output phase):
```python
"fusion":          0.2,
```
Then update `pipeline.py:106` from `.get("fusion", 0.1)` to direct dict access `PHASE_TEMPERATURES["fusion"]` to make missing keys fail loudly.

---

### 6. Fix deep_read token inconsistency in search_phases.py [MEDIUM]

**File:** `src/reasoner/application/flows/search_phases.py` — lines 361, 397, 422

**Problem:** Three calls within the same deep_read phase use inconsistent `max_tokens`: 1024, 1024, and 512. The canonical budget `PHASE_TOKEN_BUDGETS["deep_read"]` = 2048.

**Fix:** Replace the two full deep_read calls (lines 361, 397) with `get_token_budget("deep_read")`. The shallow fallback (line 422) is intentionally smaller — add a new canonical entry `"deep_read_shallow": 512` and use `get_token_budget("deep_read_shallow")` there.

```python
# In constants_limits.py PHASE_TOKEN_BUDGETS:
"deep_read_shallow": 512,

# In search_phases.py:
from reasoner.core.constants import get_token_budget
max_tokens=get_token_budget("deep_read"),         # lines 361, 397
max_tokens=get_token_budget("deep_read_shallow"), # line 422
```

---

### 7. Add missing phase budget entries [MEDIUM]

**File:** `src/reasoner/core/constants_limits.py` — `PHASE_TOKEN_BUDGETS` dict

Three roles have inline `max_tokens` literals with no matching entry:

| Role | Current inline value | Recommended canonical value |
|------|---------------------|----------------------------|
| `"prism_classify"` | 256 (prism_classifier.py:68) | 256 |
| `"recovery_path"` | 1024 (jury_phases.py:39, recovery_service.py:38) | 1024 |
| `"search_disambiguation"` | 256 (search_phases.py:132) | 256 |

Add to `PHASE_TOKEN_BUDGETS`:
```python
"prism_classify":         256,
"recovery_path":         1024,
"search_disambiguation":  256,
```

Then update each call site to use `get_token_budget("prism_classify")` etc.

**Call sites to update:**
- `src/reasoner/application/services/prism_classifier.py:68`
- `src/reasoner/application/flows/jury_phases.py:39`
- `src/reasoner/application/services/recovery_service.py:38`
- `src/reasoner/application/flows/search_phases.py:132`

---

### 8. Move `TOKEN_OPTIMIZATION` flags to `Settings` [MEDIUM]

**File:** `src/reasoner/core/settings.py` + `src/reasoner/application/pipeline.py`

**Problem:** `TOKEN_OPTIMIZATION` is a hardcoded dict in `pipeline.py` with no env-variable control. These are runtime behavior switches that belong in `Settings`.

**Fix — add to `Settings` class in `settings.py`:**
```python
# Token optimization flags
TOKEN_DYNAMIC_BUDGETS: bool = os.getenv("TOKEN_DYNAMIC_BUDGETS", "true").lower() == "true"
TOKEN_CONTEXT_COMPRESSION: bool = os.getenv("TOKEN_CONTEXT_COMPRESSION", "true").lower() == "true"
TOKEN_PROMPT_COMPRESSION: bool = os.getenv("TOKEN_PROMPT_COMPRESSION", "true").lower() == "true"
TOKEN_NEURO_COMPRESSION: bool = os.getenv("TOKEN_NEURO_COMPRESSION", "false").lower() == "true"
TOKEN_CACHING: bool = os.getenv("TOKEN_CACHING", "true").lower() == "true"
```

**Fix — update `pipeline.py`** to build `TOKEN_OPTIMIZATION` from settings instead of hardcoding:
```python
from reasoner.core.settings import settings
TOKEN_OPTIMIZATION = {
    "dynamic_budgets":     settings.TOKEN_DYNAMIC_BUDGETS,
    "context_compression": settings.TOKEN_CONTEXT_COMPRESSION,
    "prompt_compression":  settings.TOKEN_PROMPT_COMPRESSION,
    "neuro_compression":   settings.TOKEN_NEURO_COMPRESSION,
    "caching":             settings.TOKEN_CACHING,
}
```
All downstream consumers (`synthesis_phase.py`, `perspective_phases.py`, etc.) that import `TOKEN_OPTIMIZATION` from `pipeline.py` or `reasoner.pipeline` continue to work unchanged.

---

## Files Modified (Summary)

| File | Nature of Change |
|------|-----------------|
| `src/reasoner/core/constants_models.py` | Add `MODEL_CLAUDE_HAIKU` |
| `src/reasoner/core/constants_limits.py` | Fix `QUALITY_JUDGE_MODELS["premium"]`; add 4 new `PHASE_TOKEN_BUDGETS` entries |
| `src/reasoner/core/temperatures.py` | Add `"fusion": 0.2` to `PHASE_TEMPERATURES` |
| `src/reasoner/core/settings.py` | Fix `NEURO_REASONING_MODEL` default; add 5 `TOKEN_*` flags |
| `src/reasoner/neuro/config.py` | Replace 2 raw model paths with alias constants |
| `src/reasoner/application/pipeline.py` | Replace hardcoded `TOKEN_OPTIMIZATION` dict with settings-driven version; fix `fusion` temperature lookup |
| `src/reasoner/application/flows/search_phases.py` | Replace 4 inline `max_tokens` with `get_token_budget(...)` |
| `src/reasoner/application/flows/jury_phases.py` | Replace `max_tokens=1024` with `get_token_budget("recovery_path")` |
| `src/reasoner/application/services/prism_classifier.py` | Replace `max_tokens=256` with `get_token_budget("prism_classify")` |
| `src/reasoner/application/services/recovery_service.py` | Replace `max_tokens=1024` with `get_token_budget("recovery_path")` |

---

## Execution Order

Execute strictly in this order to avoid import errors:

1. `constants_models.py` — add `MODEL_CLAUDE_HAIKU`
2. `constants_limits.py` — fix quality judge, add budget entries
3. `temperatures.py` — add `"fusion"`
4. `settings.py` — fix model default, add TOKEN_* flags
5. `neuro/config.py` — use new constants (needs step 1 done)
6. `pipeline.py` — use settings for TOKEN_OPTIMIZATION, fix fusion lookup (needs steps 3+4 done)
7. Call sites — `search_phases.py`, `jury_phases.py`, `prism_classifier.py`, `recovery_service.py` (needs step 2 done)

---

## Verification

```bash
# 1. Import smoke test — confirms no broken imports
python -c "from reasoner.core.constants_models import MODEL_CLAUDE_HAIKU; print('OK')"
python -c "from reasoner.core.temperatures import PHASE_TEMPERATURES; assert 'fusion' in PHASE_TEMPERATURES"
python -c "from reasoner.application.pipeline import TOKEN_OPTIMIZATION; print(TOKEN_OPTIMIZATION)"

# 2. Full test suite
python -m pytest tests/ -v -m "not slow and not integration"

# 3. Specifically verify neuro config loads without errors
python -c "from reasoner.neuro.config import NeuroConfig; c = NeuroConfig(); print('neuro config OK')"

# 4. Verify quality judge model resolves through registry
python -c "
from reasoner.core.constants_limits import QUALITY_JUDGE_MODELS
from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST
for k, v in QUALITY_JUDGE_MODELS.items():
    assert v in _MODEL_WHITELIST, f'Model alias {v!r} not in registry!'
print('All quality judge models resolve OK')
"
```
