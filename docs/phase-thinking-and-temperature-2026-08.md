# Which Phases Need Thinking, and What Temperature They Should Run At

Companion to `model-capability-per-phase-2026-08.md`. Two questions: which preset
phases genuinely benefit from reasoning tokens, and what temperature each should use.

**Headline: the config is already right. It is mostly not wired.**
`core/temperatures.py` declares tuned values for 16 phases and reasoning effort for 15.
Only **4 phases** can actually receive them, and the reasoning-model temperature floor
is dead code.

---

## 1. What is wired today

`application/pipeline.py` declares `PhaseConfig` objects for exactly four roles:

```
classification · decomposition · synthesis · fusion
```

`infrastructure/llm/executor.py:104-147` has two branches:

| Branch | Condition | Sets temperature? | Sets reasoning effort? |
|---|---|---|---|
| `elif cfg:` | a `PhaseConfig` exists | yes (+ retry strategy) | **yes** |
| `if cfg is None and lookup in PHASE_TEMPERATURES` | no PhaseConfig, but phase is in the table | yes | **no** |

Effort injection lives only in the first branch. So **11 of the 15 configured
reasoning efforts never reach a provider**:

`scoring` · `critic` · `verifier` · `meta_evaluator` · `stress_testing` ·
`perspective` · `generator` · `research` · `deep_read` · `context_vetting` ·
`recovery_path`

Every one of those is configured `high` or `medium` in `PHASE_REASONING_EFFORT`, and
every one is a judgement or integration role — exactly the set the file's own docstring
says should think hardest.

### Dead code

`temperature_for()` and `reasoning_extra_body()` have **zero callers** anywhere in
`src/`. That makes `REASONING_TEMPERATURE_FLOOR = 0.6` inert — the documented
protection against starving a reasoning model at `critic=0.1` / `verifier=0.2` has
never run.

### Precedence, once effort *is* set

`infrastructure/llm/router.py:141-145` temporarily merges the per-call `extra_body`
over the provider's: `{**provider.extra_body, **extra_body}`. So a phase-level effort
**wins** over a registry-level one. That matters because the DeepSeek entries hardcode
`{"reasoning": {"effort": "high"}}` in the whitelist:

- `fusion` (has a PhaseConfig, effort `minimal`) correctly overrides DeepSeek's `high`.
  Good — `fusion` is a 1,536-token mechanical merge and does not need max thinking.
- `scoring` on `deepseek-v4-flash` (20 budget presets) has no PhaseConfig, so DeepSeek's
  hardcoded `high` applies. Right outcome, reached by accident.
- Every **non-DeepSeek** model in those 11 phases gets the provider default. After the
  2026-08-18 routing change that is most of the premium critique path:
  `glm-5.2` scoring ×19, `grok-4.20` verifier ×18, `grok-4.6` stress_testing ×20,
  `gemini-2.5-flash-lite` verifier ×20, `qwen3.7-flash` meta_evaluator ×20 — all
  configured `high`, all running on defaults.

### Temperature that never lands

`providers/openai_compat.py:168` denylists models that reject a custom temperature:

```
"gpt-4", "gpt-5", "/o1", "/o3", "/o4", "claude-opus", "claude-fable", "pareto-code"
```

`synthesis` is configured at 0.5. Its model matches `gpt-5` (`gpt-5.6-luna`, 41 presets),
so the value is dropped. **Not a regression** — the previous model, `gpt-4o-mini`,
matched `gpt-4`. Synthesis temperature has never been applied in those presets; the
model's own default has always been in force.

---

## 2. Which phases actually need thinking

Reasoning tokens are not free: they add latency, raise output cost, consume context, and
**make simple tasks worse through overthinking**. The 2026 guidance is to pick a
reasoning tier per task, not per project.

The relevant asymmetry for this pipeline: *classifying is easier than generating*. A
model that cannot produce a perfectly factual answer can still reliably detect that an
answer contradicts a retrieved document — which is why cheap verifiers work at all, and
why `gemini-2.5-flash-lite` at 3.3% HHEM is a defensible budget verifier.

| Phase | Out budget | Needs thinking? | Why |
|---|---|---|---|
| `synthesis` | 32768 | **high** | Integrates every prior phase, emits epistemic labels. Highest-stakes output in the run |
| `stress_testing` | 1024 | **high** | Adversarial search — the whole value is finding a failure the generator missed |
| `scoring` / `critic` | 1024 | **high** | Independent judgement; reasoning judges measurably beat non-reasoning ones on non-verifiable rubrics |
| `verifier` | 1024 | **high** | High-risk boundary — this is the last check before user-facing output |
| `meta_evaluator` | 1024 | high | Judges the judges |
| `deep_read` | 2048 | medium | Retrieval fidelity over long context; depth helps, but input dominates cost |
| `research` | 4096 | medium | Grounded retrieval; the search backend does the heavy lifting |
| `perspective` / generators | 1536 | medium | Some reasoning aids cross-lab diversity, but diversity comes from *sampling*, not depth |
| `decomposition` | — | low | Structure extraction |
| `context_vetting`, `recovery_path` | — | low | Bounded checks |
| `classification`, `fusion`, `prism_classify` | 256–1536 | **minimal** | Routing and mechanical merge. Overthinking here is pure waste |

This is what `PHASE_REASONING_EFFORT` already says. The table is not the problem.

Placement guidance worth adopting: judge checks belong at three boundaries — before
user-facing output, before irreversible tool execution, and on writes to persistent
memory — rather than on every intermediate step. Reasoner's `post_synthesis_verify`
(all 50 presets) is exactly the first boundary; the Neuro `/neuro/learn` write at
pipeline end is the third and currently has no verification gate.

---

## 3. Optimal temperatures

Evidence, and how it lands against the current table:

- **Zero-shot peaks at moderate temperature** — ~59% accuracy at T = 0.4–0.7. Chain-of-thought
  behaves differently, performing best at the extremes.
- **Extended reasoning benefits from higher temperature**, not lower: the measured
  benefit of extended reasoning rises from 6× at T = 0.0 to **14.3× at T = 1.0**.
- **Greedy decoding wins single-pass** reasoning and coding. But self-consistency with
  nucleus sampling at a controlled temperature beats greedy single-pass by **9–15
  points absolute** — which is the regime Reasoner actually runs in, since Phase 2
  samples multiple perspectives and Phase 3 prunes.
- **DeepSeek-R1 guidance: temperature 0.6, top-p 0.95.**

Verdict on `PHASE_TEMPERATURES`:

| Phase | Current | Assessment |
|---|---|---|
| `perspective` | 1.0 | **Correct.** Diversity is the product here, and multi-sample + prune is exactly the regime where sampling beats greedy |
| `generator` | 0.7 | Correct — top of the moderate band |
| `synthesis` | 0.5 | Reasonable, but **never applied** (denylist). Moot until the model changes |
| `stress_testing` | 0.5 | Reasonable |
| `classification` 0.3 / `decomposition` 0.4 | | Correct — in the 0.4–0.7 zero-shot band or just under, and these want repeatability |
| `critic` | **0.1** | **Too low for a reasoning model.** This is precisely the case `REASONING_TEMPERATURE_FLOOR` was written for, and the floor is dead code |
| `verifier` | **0.2** | Same problem. `grok-4.20` and `glm-5.2` both run internal CoT |
| `fusion` | 0.2 | Fine — mechanical merge, wants determinism |
| `deep_read` | 0.2 | Fine — extraction, not generation |

The single highest-value fix is not a new number. It is **calling the function that
already exists**: `temperature_for(phase, is_reasoning_model=True)` would lift `critic`
0.1 → 0.6 and `verifier` 0.2 → 0.6 for exactly the models that need it, matching
DeepSeek's published 0.6 and the "reasoning benefits from higher T" finding.

---

## 4. Recommended changes

Ordered by leverage. None applied — this document is research only.

1. **Move effort injection out of the `elif cfg:` branch** in `executor.py` so the
   `cfg is None` path also sets `PHASE_REASONING_EFFORT.get(lookup)`. One-branch change;
   unblocks all 11 unwired phases at once.
2. **Wire `temperature_for()`** with a real `is_reasoning_model` predicate, so the 0.6
   floor stops being dead code. Needs a reasoning-model set — derivable from
   `supported_parameters` in the bundled catalogue, which already carries it.
3. **Declare PhaseConfigs for the judgement roles** (`scoring`, `verifier`, `critic`,
   `meta_evaluator`, `stress_testing`) rather than relying on the flat-table fallback, so
   they also get retry temperature strategies.
4. **Make `_FIXED_TEMPERATURE_MARKERS` data-driven** off `supported_parameters` instead
   of substring matching. The current list is a maintenance trap: `"gpt-5"` silently
   captures every future `gpt-5.x`, and no `:batch` variant matches it even though batch
   lanes drop `temperature` — the exact bug the Aug catalogue doc flagged.
5. **Consider a verification gate on the Neuro `/neuro/learn` write** — persistent-memory
   writes are one of the three boundaries where judging pays for itself, and there is
   none today.

**Not verified at runtime.** All of the above is read from source. Confirming the
unwired-effort claim end to end wants one live run with request logging on a premium
preset, checking whether `reasoning.effort` appears in the `scoring` call body.
