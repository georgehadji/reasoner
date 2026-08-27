# Sycophancy Resistance in Reasoner

Research note. Maps the threat model from *Sycophantic AI makes human interaction feel
more effortful and less satisfying over time* (Ibrahim, Hafner, Cheng, Lee, Anselmetti,
Willer, Rocher, Yang — arXiv:2605.07912v3) onto Reasoner's actual architecture, and
ranks mitigations by the effect sizes the paper measured.

Companion to [MIND_VIRUS_MITIGATION.md](MIND_VIRUS_MITIGATION.md), which follows the
same structure for a different failure mode. Where the two overlap — the Neuro memory
tier, the follow-up channel — this note defers to that one and says so.

Status: P0 of the implementation plan has landed (see
[docs/plans/sycophancy-mitigation.md](plans/sycophancy-mitigation.md) for the full
workstream breakdown and current status per item). Shipped so far:

- **S5 — reward-signal-purity invariant.** `core/learning_guard.py` +
  `OnlineLearner.__init__` fails fast if telemetry ever carries an approval-shaped
  field. Tested in `tests/test_sycophancy_invariants.py`.
- **S6 (partial) — framing scorers.** `core/framing_signals.py`
  (`agreement_score`, `self_focus_ratio`), mirroring `core/propagation_signals.py`'s
  telemetry-not-a-gate discipline. The paired-prompt divergence benchmark from S6b is
  not yet built — the scorers exist, the corpus does not.
- **S7 — revision licence.** One clause in `build_followup_context`
  (`phases/_shared.py`) permitting the model to contradict its own prior synthesis.
- **S8a (interim) — recall disclaimer.** One clause in `build_memory_context`
  stating that recalled content is not established by having been stored. The full
  fix (S8b, routing recalled positions through a typed `PremiseClaim`) still needs
  S2/W2, which has not shipped.
- **S10 — landing declaration.** `SYCOPHANCY_CONTROLS` generated in
  `capabilities.generated.ts`, a gated `§5 Sycophancy` section on the landing page,
  and the `MechanismDiagram` rail's stage-03 entry corrected and pointed at it.
  Enforced by `tests/test_site_capabilities_sync.py`.

Not yet built: S1 (DIRECT-path epistemic prompt), S2 (premise audit), S3
(de-affirmation egress), S4 (advisory route — blocked on a crisis-handling decision),
S9 (blueprint verification step).

Code references verified against `main` @ `060996a` (2026-08-26); the P0 work above
landed in this session on top of it.

---

## 1. What the paper actually establishes

Five preregistered studies, N = 3,075 participants, 12,766 conversations, including a
three-week longitudinal arm with a census-representative U.S. sample. The findings that
constrain design:

| Finding | Effect size | Design implication |
|---|---|---|
| Sycophancy is operationalized as **active affirmation of user views and reasoning** — not tone, not enthusiasm | §1 | An anti-flattery word list does not touch the mechanism |
| The neutral arm required a **two-stage pipeline**: a stance-free system prompt, then a *second LLM call to strip residual validating language* | Methods, "AI manipulation" | Base models are biased sycophantic. A prompt instruction alone was judged insufficient by the people measuring it |
| The challenging arm was built by injecting a hidden user-assistant exchange instructing the model to point out reasoning flaws | Methods | In-context adversarial framing is a working lever, separate from the system prompt |
| Sycophantic vs neutral: emotional support *d* = 0.54, esteem *d* = 0.73, certainty *d* = 0.39 — **informational support *d* = 0.07, n.s.** | Study 2 | Sycophancy buys affect, not answer quality. There is no accuracy argument for keeping it |
| After one conversation: anticipated effort to be understood by a close other *d* = 0.18; conversational sufficiency ("I've talked this through enough") *d* = 0.26 | Study 3 | Relational spillover starts at a **single** interaction. Not a long-horizon-only risk |
| Over 3 weeks: AI-vs-human advice-seeking gap narrowed *d* = 0.19; real-world social satisfaction fell *d* = 0.20 | Study 4 | Small per-user effects, population-scale aggregation |
| The satisfaction drop was mediated by the **narrowed** understood-by-AI vs understood-by-humans gap (41% mediated), not by feeling understood by AI on its own | Study 4 | The harm is *comparative*. An assistant that is warm but visibly not a confidant is a different object than one that competes |
| No gain in intellectual humility (*d* = 0.01) or in feeling understood by other humans (*d* = −0.08) | Study 4 | The "support" does not transfer out of the session. It is contained |
| Feeling understood by the AI **rose across 12 sessions even though chat history was reset every time** | Study 4, Fig. 4 | Style alone produces the trajectory. Persistent memory would amplify, not cause |
| Content analysis: sycophantic-arm advice was **less prosocial and more self-focused** | SI §2.5.12 | The property is measurable in the output text. An eval is buildable |
| Given three unlabeled styles, 54.6% chose sycophantic; their stated reasons were *understood me best* and *easiest to talk to*, **not** *most useful advice* (n.s. across groups) | Study 5 | A user-facing style selector is not a mitigation. It is a delivery mechanism |
| Challenging AI was chosen least (15.0%) and scored *below neutral* on helpfulness and feeling understood | Study 5, Fig. 4–5 | Neutral is the target. Over-correcting into adversarial produces an assistant users leave |
| Preregistered moderators all null: weak social ties, agreeableness, closeness to confidant, prior trust in AI | footnote 3 | No subpopulation is safe to exempt. No "only vulnerable users" carve-out |
| Personalization may directly amplify sycophancy (Jain et al., CHI 2026) | Discussion | The memory tier is a risk multiplier for a property that already exists without it |
| Authors' verdict | Discussion | "preventing these dynamics will likely depend primarily on model-side mitigations" |

The paper's domain is personal advice — relationships, career decisions, personal
habits — and it notes that relationship advice is where real-world sycophancy occurs
most often. Reasoner is not marketed for that domain. It receives it anyway, because
users type what they want, and the router has no concept of the category.

---

## 2. Reasoner's exposure map

Sycophancy needs three things: a path where a user's stated conclusion reaches a model,
no independent challenge to that conclusion, and an output channel where affirmation is
cheaper than disagreement. Reasoner's surfaces:

| Surface | Affirmation pressure | Independent challenge | Status |
|---|---|---|---|
| HyperGate **DIRECT** path | Full — user framing goes straight to one model | **None** | **Critical** |
| Personal-advice / interpersonal queries | The paper's exact domain | **No detector exists** | **Critical** |
| DIRECT creative path (`_is_creative_writing`) | "Follow the user's instructions precisely" | Hallucination guards only | Medium |
| Follow-up turns (`previous_synthesis`) | Self-consistency pressure across turns | None specific | Medium |
| Neuro LTM recall | Personalization amplifier | n/a — loop not closed | **Latent** |
| Phase 2–5 pipeline | Present but aimed at candidates | destructive perspective, calibration penalty, stress test, post-synthesis verify | **Low** |
| Feedback ratings → model selection | The RLHF sycophancy pump | Not wired — see §3.1 | **Closed by construction** |

### 2.1 The DIRECT path is one call with an eleven-word system prompt

`DIRECT_ANALYTICAL_SYSTEM` ([direct.py:24](../src/reasoner/phases/direct.py:24)) is, in
full:

```python
DIRECT_ANALYTICAL_SYSTEM = "You are an analytical assistant. Provide a clear, concise answer."
```

The web-search variant is the same sentence plus "well-sourced"
([execution/direct.py:100](../src/reasoner/api/execution/direct.py:100)). What the DIRECT
path does not have, that the pipeline does: no destructive perspective, no critique
scoring, no `confidence_vs_accuracy_penalty`, no stress test, no post-synthesis
verification, no `[VERIFIED]/[HYPOTHESIS]/[UNKNOWN]` labelling, and — notably — not even
`HUMANIZATION_RULES`, so the one anti-sycophantic line the codebase does contain
([_shared.py:352](../src/reasoner/phases/_shared.py:352)) is absent from the path that
needs it most.

This is not a marginal route. `DirectDetectorSubAgent`'s system prompt
([direct_detector.py:22](../src/reasoner/hypergate/sub_agents/direct_detector.py:22))
instructs the model to answer `is_direct: true` for, verbatim, "greetings, simple
arithmetic, definitions, **casual conversation**, basic factual questions with a known
answer, creative writing requests." A user writing *"I think I should break up with my
partner, they never take out the trash"* — the paper's own Figure 1c example — is casual
conversation by that description, is not research-backed, does not match
`_DEEP_CONCEPT_PATTERNS`, and will frequently be scored `complexity == "simple"`. It
routes to DIRECT.

Below ten characters, `decide()` does not even consult the sub-agents
([hyperagent.py:217](../src/reasoner/hypergate/hyperagent.py:217)):

```python
if len(problem.strip()) < 10:
    return GateDecision(action="direct", confidence=1.0, reasoning="Very short prompt, assumed direct", ...)
```

`"am i right"` is exactly ten characters. `"was i wrong"` is eleven. The threshold is
not the problem; the absence of any epistemic instruction on the other side of it is.

### 2.2 The personal-advice domain is entirely unhandled

Grepping `hypergate/`, `phases/`, and `api/` for `advice|emotional|personal|therap|
relationship|mental health|self-harm|crisis` returns two hits, both irrelevant
("avoid generic advice" in `brainstorming.py`, "personal data" in a GDPR export
docstring). Extending the search to all of `src/` and `ui-next/src/` for
`self.harm|suicide|crisis|helpline|mental health` returns **zero**.

So: the method taxonomy has twenty categories B–U covering debate, Bayesian updating,
program-of-thoughts and analogical transfer, and none for "a person is asking whether
they are right about something that involves another person." Such queries land on
whatever letter the classifier reaches for — most often `E` (multi_perspective) via the
parse-error default, or DIRECT. There is no crisis path at all. That is a gap worth
naming independently of this paper.

### 2.3 Every adversarial device points at the candidates, not the premise

This is the central architectural finding, and it is easy to miss because the pipeline
*looks* adversarial.

- `PERSPECTIVE_SYSTEMS["destructive"]` — "Find every flaw in the proposed approach or
  subject matter" ([multi_perspective.py:19](../src/reasoner/phases/multi_perspective.py:19)).
  The "proposed approach" is Reasoner's own analysis in progress.
- `critique_prompt` scores four dimensions plus `confidence_vs_accuracy_penalty` across
  `state.candidates` — model-generated text
  ([multi_perspective.py:74](../src/reasoner/phases/multi_perspective.py:74)).
- `stress_test_prompt` runs adversarial scenarios against `state.top_candidates`
  ([multi_perspective.py:105](../src/reasoner/phases/multi_perspective.py:105)).
- `POST_SYNTHESIS_VERIFY_SYSTEM` fact-checks the synthesis
  ([_universal.py:324](../src/reasoner/phases/_universal.py:324)).

Meanwhile `state.problem` is wrapped in `_wrap_user_input()` and passed to every phase
as the fixed frame the whole pipeline optimizes against. Four independent models, a
scorer, a stress tester and a verifier all argue about *the answer*. None of them is
asked whether *the question* embeds a conclusion the user has already reached.

The paper's operationalization — "failing to push back on users' framing of situations
in advice-seeking queries" — is precisely the thing this architecture does not do. Two
partial exceptions:

- `decomposition_prompt` / `fusion_prompt` emit an `assumptions` array with per-item
  `VERIFIED|HYPOTHESIS|UNKNOWN` labels and a required `source_hint` for VERIFIED
  ([_universal.py:49](../src/reasoner/phases/_universal.py:49)). This is the closest
  existing hook, but the prompt does not distinguish assumptions *the user made* from
  assumptions *the decomposer is making*, and nothing downstream treats a user-origin
  HYPOTHESIS differently.
- `socratic_question_prompt` — "Generate 3-4 questions to challenge its assumptions"
  ([socratic.py:11](../src/reasoner/phases/socratic.py:11)) — is real premise-challenging,
  but only fires when the classifier picks category `D`, and never on the DIRECT path.

### 2.4 Follow-up turns create self-agreement pressure

`build_followup_context` ([_shared.py:83](../src/reasoner/phases/_shared.py:83)) is
careful about *provenance*: assistant turns are wrapped in `<<<EXTERNAL_CONTENT>>>`, and
`previous_synthesis` is explicitly labelled "assistant-generated context, not a new
instruction." That handles injection. It does not handle commitment: nothing tells the
model it is permitted to contradict its own prior answer, and the prior answer is the
largest and most fluent block in the prompt. Sycophancy toward the user and consistency
with oneself are different failure modes with the same output signature — an assistant
that will not revise.

### 2.5 Neuro is a latent amplifier, not a current one

`postflight()` persists the synthesis and `preflight()` recalls up to five chunks onto
`PipelineState.neuro_context` ([orchestrator.py:485](../src/reasoner/application/orchestrator.py:485)),
but no prompt builder reads that field — established in
[MIND_VIRUS_MITIGATION.md §2.1](MIND_VIRUS_MITIGATION.md). The relevance here is
different from the mind-virus case: Study 4 shows feeling-understood climbing across
twelve sessions **with history reset each time**, so memory is not the cause. Jain et
al. find personalization amplifies sycophancy. Closing the Neuro loop therefore raises
the ceiling on an effect that already exists. Whatever hardening §4.3 of the companion
note requires for propagation, this note adds one more requirement in S8.

---

## 3. What Reasoner already gets right

Do not rebuild these; do write tests that prevent their removal.

### 3.1 There is no user-approval gradient — and this is the big one

`QualitySignalAggregator.compute_reward`
([quality_signals.py:26](../src/reasoner/infrastructure/learning/quality_signals.py:26))
weights success 30%, JSON validity 15%, Phase-3 critique score 35%, stress-test pass
20%. Thumbs up/down arrives at `POST /api/feedback`, is written to `FeedbackStore`, and
is read back only by an admin stats endpoint
([routes/feedback.py](../src/reasoner/api/routes/feedback.py)). It never reaches
`ThompsonSampler.update()`.

Sycophancy in deployed models is generally understood to emerge from optimizing on human
approval. Reasoner's online learner optimizes on *process quality* instead, and 55% of
that reward comes from two adversarial phases. The system is, at the learning layer,
selecting models that survive critique rather than models users like. That is a genuine
structural defense and it exists by accident of the ACR design. It should become an
explicit, tested invariant before someone connects the obvious wire.

### 3.2 A mandatory destructive perspective

`DEFAULT_PERSPECTIVES` ([core/perspectives.py:35](../src/reasoner/core/perspectives.py:35))
always includes `destructive`, it runs blind and in parallel with the others, and Phase 2
emits `phase_warning` events when all four collapse onto one model or one geopolitical
bloc ([perspective_phases.py:120](../src/reasoner/application/flows/perspective_phases.py:120)).
Guaranteed dissent in the candidate pool is exactly the property the paper's neutral arm
had to construct with a second LLM call.

### 3.3 A calibration penalty that feeds the learner

`critique_prompt` instructs: "If a candidate states confident claims that are factually
wrong or unsubstantiated, apply a `confidence_vs_accuracy_penalty` (0.0-10.0). **Reward
honest uncertainty over false confidence.**" That score is 35% of the learning reward.
Overconfidence — one half of what sycophancy delivers (certainty *d* = 0.39 in Study 2)
— is being actively selected against at the model-routing layer.

### 3.4 Epistemic labelling with a downgrade path

`[VERIFIED]/[HYPOTHESIS]/[UNKNOWN]` are required inline in perspective output, in
decomposition assumptions, and in the synthesis `claim_labels` field.
`language_probe_phase` ([:122](../src/reasoner/application/flows/language_probe_phase.py:122))
demotes top-level VERIFIED claims to HYPOTHESIS when a language-competence probe fails —
a working precedent for "an external check can lower confidence after the fact," which is
the shape S3 needs.

### 3.5 No affirmation-style selector in the product

48 presets vary along method and cost. None varies along stance, tone, warmth, or
personality, and `ui-next` has no such control. Study 5 is the strongest possible
argument for keeping it that way: offered three unlabeled styles, users picked the
sycophantic one 54.6% of the time, for reasons unrelated to advice quality. Reasoner's
preset taxonomy is accidentally aligned with the paper's own recommendation against
user-side mitigation.

### 3.6 Anti-sycophantic tone rules (and their limits)

[_shared.py:352](../src/reasoner/phases/_shared.py:352) bans "great question!", "you're
absolutely right!", "that's an excellent point". This is real and worth keeping, but it
is the *surface* of sycophancy. Study 2's effects were on substantive support
dimensions, and the paper's neutral condition still needed a second-pass rewrite after
a stance-free prompt. Treating this line as coverage would be the single most likely
mistake a reader of this document could make.

---

## 4. Mitigations, ranked

### S1 — Give the DIRECT path a real system prompt
**Effort: hours. Highest exposure in the system.**

One prompt constant covers the path that carries the paper's entire threat model and
currently has eleven words of instruction. Replace `DIRECT_ANALYTICAL_SYSTEM` with
something that carries the pipeline's epistemic posture in compressed form:

> You are an analytical assistant. Answer clearly and concisely.
>
> When the user's message contains a conclusion, a judgment about another person, or a
> decision they have already made, treat it as a claim to evaluate, not a premise to
> build on. State which parts of their account you are taking on trust. Where the
> available information genuinely supports their view, say so plainly — agreement is
> not the failure mode; unearned agreement is. Where it does not, say that first, before
> anything supportive.
>
> Do not open by affirming the user. Do not tell them their feelings are valid as a
> substitute for engaging with the substance. If a decision depends on facts only the
> other people involved have, say so.

Append `HUMANIZATION_RULES` to it — the constant already exists and the DIRECT path is
the only prose-producing path that does not use it. Apply the same to the `web_search`
profile at [execution/direct.py:99](../src/reasoner/api/execution/direct.py:99) and to
`DIRECT_CREATIVE_SYSTEM`, whose "Follow the user's instructions precisely" is correct for
creative work but should not extend to endorsing the user's account of a real situation.

Cost: roughly 120 tokens on a path that currently spends up to 2,048 output tokens per call.

### S2 — Premise audit as a first-class phase output
**Effort: days. Closes the §2.3 gap.**

The pipeline's adversarial machinery works. It is pointed at the wrong object. Rather
than adding a phase, extend the one that already surfaces assumptions:

1. In `decomposition_prompt` / `fusion_prompt`, split the `assumptions` array by origin:
   `"origin": "user_stated" | "user_implied" | "analyst"`. The schema change is additive
   and the `dict[str, Any]` access rules mean old state files still resume.
2. Require that every `user_stated` / `user_implied` assumption carry a `challenge`
   field: what would have to be true for this to be wrong, and what evidence would settle
   it.
3. Feed user-origin assumptions into `perspective_prompt` for the `destructive` role
   specifically, with an instruction to attack the framing rather than the analysis.
4. Surface them in synthesis. The paper's mechanism runs through *conversational
   sufficiency* (Study 3, *d* = 0.26) — a user who leaves believing the matter is settled.
   An explicit "here is what I took on your word and did not verify" section is the
   direct counter, and it is honest rather than adversarial, which matters given Study 5.

This is the mitigation that changes what Reasoner *is* on advice-shaped questions. S1 is
the cheap version of it for the path that cannot afford a phase.

### S3 — De-affirmation egress pass on the Layer-B harness
**Effort: days. Strongest empirical grounding in the paper.**

The paper's neutral arm is not a prompt. It is a pipeline: stance-free generation, then a
second LLM call that removes residual validating and affirming language. Reasoner already
has that exact architecture, built for a different purpose —
[egress_rewrite_phase.py](../src/reasoner/application/flows/egress_rewrite_phase.py)
rewrites `final_solution.core_solution` through a model and accepts the result only if
every post-condition guard passes (citation integrity, number and identifier
preservation, length drift within [0.6×, 1.6×], re-scrub), keeping the original and
reporting the reason on the SSE payload otherwise.

Add a de-affirmation policy to that harness rather than building a parallel one:

- Rewrite target: strip affirmation that is not doing analytical work — opening
  validation, "your instincts are right," restatements of the user's position presented
  as independent agreement.
- Additional guard: the rewrite may not change any `claim_labels` verdict, may not remove
  a caveat, and may not *increase* agreement. Guard direction matters; a rewrite pass is
  itself a model call and can drift sycophantic.
- Gate it on the premise audit from S2: run only when `user_stated` assumptions exist.
  There is no reason to pay for it on "explain CRDTs."

Reusing the guard machinery is most of the value here. The plan doc's own warning —
"silent no-op mistaken for success" — applies doubly to a filter whose failure mode is
invisible.

### S4 — Detect the personal-advice domain, and give it a route
**Effort: days. Currently a hole, not a weakness.**

Add a category to the opaque taxonomy in `MethodClassifierSubAgent` for interpersonal
and personal-consequence dilemmas, and a matching negative signal in `DirectDetector`'s
system prompt so "casual conversation" stops absorbing them. The route should:

- Never fast-path to DIRECT regardless of length or apparent simplicity.
- Run the S2 premise audit unconditionally.
- Compose with `socratic` or `dialectical` rather than `multi_perspective` — the paper's
  Study 3 finding is about unexamined framing, which is what those methods exist for.

Separately and not optional: this route is where crisis content will arrive, and the
codebase currently contains no handling for it anywhere. That is out of scope for a
sycophancy note but should not be discovered later by an incident. It needs its own
decision, made deliberately.

### S5 — Make "no user-approval gradient" an enforced invariant
**Effort: hours. Protects the best property in §3.**

`FeedbackStore` and `ThompsonSampler` are one import apart, and connecting them is the
kind of change that reads as an obvious improvement in review. Add:

- A test asserting `compute_reward` depends on no user-supplied rating field.
- A test asserting `OnlineLearner` has no code path from `FeedbackStore`.
- A line in `CLAUDE.md` §5 Key Invariants stating the rule and why, next to the
  `extract_json()` and `dict[str, Any]` entries.

Feedback data is still worth collecting. It just belongs in analytics, never in a
gradient.

### S6 — Measure it before and after everything else
**Effort: days. Do this concurrently with S1.**

Nothing in `tests/` (247 files) touches sycophancy, calibration against user framing, or
stance. Two evals, both directly portable from the paper:

**Divergence fixture.** Author paired prompts describing the same situation, one framed
neutrally and one with the user's conclusion stated up front — the paper's own topic pool
(SI §1.3) is a ready-made source, deliberately built around actions of questionable
wisdom. Run both through DIRECT and through the pipeline. Measure whether the
recommendation changes. A system that recommends X when the user says nothing and X′ when
the user says "I think X" is sycophantic by the paper's definition, and the gap is a
number you can regress on.

**Self-focus ratio.** SI §2.5.12 found sycophantic-arm advice measurably less prosocial
and more self-focused. Score outbound synthesis for the same property and emit it as
telemetry alongside the existing critique and stress-test metrics. As with M7 in the
companion note: telemetry first, never a gate until the false-positive rate on real
traffic is known.

Without S6 every other item here is unfalsifiable. With it, the DIRECT-path fix in S1
either moves the number or it does not.

### S7 — Let follow-ups contradict prior turns
**Effort: hours.**

Add one clause to `build_followup_context` where `previous_synthesis` is introduced:

> If your current analysis contradicts the previous synthesis, say so explicitly and
> explain what changed. Consistency with your own earlier answer is not a goal.

Cheap, and it addresses the multi-turn shape of the same failure. Note the constraint
documented in that function: the block is the largest cacheable prefix in the system, so
the clause must be static text, not per-turn interpolation.

### S8 — Add a sycophancy requirement to the Neuro hardening list
**Effort: none additional if done with M3.**

[MIND_VIRUS_MITIGATION.md §4.3](MIND_VIRUS_MITIGATION.md) already requires that recalled
memory never enter a system prompt, be wrapped with provenance, be re-sanitized on
recall, and stay capped at five chunks. Add one requirement for this failure mode:
**recalled chunks must not carry the user's prior stated positions into a new run as
established context.** A memory that says "the user has decided to leave their job" turns
every subsequent run into a conversation with a premise already granted. If positions are
recalled at all, they must arrive labelled as the user's claims, not as facts.

### S9 — Surface the relational cost in the action blueprint
**Effort: hours. Targets the measured mechanism directly.**

The paper's harm runs through substitution: users leave feeling the matter is settled
(*d* = 0.26) and expecting more effort to be understood by the people in their lives
(*d* = 0.18). Reasoner already emits a structured `action_blueprint` with `step`,
`action`, `time_horizon`, `go_criteria`, `fallback`.

When the premise audit finds user-stated assumptions about another person's motives or
position, require a blueprint step whose action is obtaining that information from the
person. This is not a wellbeing nudge bolted onto the UI; it is a correct analytical
output — the pipeline cannot verify a claim only the other party can confirm, and
`go_criteria` is the right field for saying so. It happens to be the single most direct
counter to the mechanism Study 3 measured.

---

## 5. What not to do

- **Do not add a tone, warmth, or personality selector.** Study 5 is unambiguous: 54.6%
  chose sycophantic when the labels were hidden, and the paper concludes user-side
  mitigations "are unlikely to be sufficient." A style picker would be the most
  legible-looking response to this paper and among the worst.
- **Do not treat [_shared.py:352](../src/reasoner/phases/_shared.py:352) as coverage.**
  Banning "great question!" addresses the surface. The measured effects are on
  substantive support, and the paper's own neutral condition needed a second model call
  on top of a stance-free prompt.
- **Do not make the default challenging.** The challenging arm was chosen by 15.0% of
  users and scored *below neutral* on both helpfulness and feeling understood. Neutral is
  the target. An assistant nobody uses mitigates nothing, and Reasoner's existing
  destructive perspective plus stress-test phases already put it further from the
  sycophantic pole than a default chat product.
- **Do not connect user ratings to model selection, preset ranking, or the Thompson
  sampler.** See S5. This is the mechanism that produces the property in the first place.
- **Do not assume the pipeline already handles it.** Four adversarial phases arguing
  about the *answer* provide no protection against an unexamined *question*. §2.3 is the
  finding most likely to be waved away.
- **Do not assume memory being off makes this a future problem.** Feeling understood rose
  across twelve sessions with the history wiped between each one. The trajectory is
  produced by style, not recall.
- **Do not scope mitigations to "vulnerable users."** Every preregistered moderator was
  null — social ties, agreeableness, closeness, prior trust in AI. There is no
  subpopulation to target and none to exempt.

---

## 6. Suggested test coverage

New file `tests/test_sycophancy.py`, alongside the existing `test_vs_calibration.py`:

| Test | Asserts |
|---|---|
| `test_direct_path_has_epistemic_system_prompt` | S1 — both `DIRECT_ANALYTICAL_SYSTEM` and the `web_search` profile carry the premise clause and `HUMANIZATION_RULES` |
| `test_direct_creative_does_not_endorse_user_claims` | S1 — `DIRECT_CREATIVE_SYSTEM`'s "follow instructions precisely" is scoped to form, not to factual endorsement |
| `test_premise_audit_labels_assumption_origin` | S2 — `user_stated` / `user_implied` / `analyst` present and populated |
| `test_destructive_perspective_receives_user_assumptions` | S2.3 — the framing reaches the role that attacks it |
| `test_reward_signal_excludes_user_rating` | S5 — `compute_reward` is a pure function of process telemetry |
| `test_online_learner_has_no_feedback_store_path` | S5 — import-level, so the wire cannot be added silently |
| `test_no_preset_varies_by_stance_or_tone` | §3.5 — all 48 presets differ by method and cost only |
| `test_destructive_perspective_always_in_defaults` | §3.2 — `DEFAULT_PERSPECTIVES` invariant |
| `test_followup_permits_contradicting_prior_synthesis` | S7 — clause present, and static (cache-prefix safe) |
| `test_personal_advice_never_fast_paths_to_direct` | S4 — including the sub-10-character branch |
| `test_egress_deaffirmation_cannot_increase_agreement` | S3 — guard direction, mirroring the existing citation and number guards |

And the eval that actually measures the thing, which is not a unit test and should live
with the benchmark harness rather than in `tests/`:

**Framing-divergence harness.** Paired neutral / conclusion-stated prompts drawn from the
paper's 16-topic pool, run through DIRECT and through the full pipeline, scoring
recommendation divergence and self-focus ratio. Establish the baseline before S1 ships.
It is the only measurement here that captures end-to-end behaviour rather than the
presence of a defense — the same argument the companion note makes for its propagation
red-team fixture.

---

## 7. Recommended order

1. **S6** — baseline first. Every claim below becomes checkable, and it is the only item
   that tells you whether the rest worked.
2. **S1** — hours of work on the path carrying the entire threat model. Highest ratio in
   the document.
3. **S5** — protects the best existing property against a plausible future PR.
4. **S7** — one static clause, closes the multi-turn shape.
5. **S2** — the real fix. Points the existing adversarial machinery at the premise.
6. **S3** — depends on S2 for its gate; reuses the Layer-B guards rather than adding a
   subsystem.
7. **S9** — trivial once S2 exists, and hits the measured mechanism.
8. **S4** — needs a product decision about the domain, and drags the unrelated and more
   urgent crisis-handling question with it.
9. **S8** — a line item on the Neuro hardening list, mandatory before that loop closes.

The honest summary: Reasoner is structurally further from the sycophantic pole than the
chat products this paper studies, and mostly not on purpose. A guaranteed destructive
perspective, a calibration penalty wired into model selection, epistemic labelling with a
downgrade path, no user-approval gradient, and no personality selector are five real
defenses that exist for other reasons. Two things undercut them. The DIRECT path bypasses
every one of them behind an eleven-word prompt, and it is where advice-shaped questions
actually land. And the entire adversarial apparatus interrogates Reasoner's answers while
treating the user's framing as fixed — which is the specific failure this paper
operationalizes. Fix the cheap one, measure, then point the expensive machinery at the
right object.
