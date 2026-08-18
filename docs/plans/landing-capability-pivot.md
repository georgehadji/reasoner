# Landing page pivot: from one-run record to capability marketing

**Status:** draft for approval
**Date:** 2026-08-18
**Supersedes:** the run-record-as-homepage thesis in `LandingPage.tsx:12-28`

---

## 0. Governing rule (unchanged from the trust remediation)

> Every claim on a marketing page must trace to code, a test, or a repo document.
> A capability that exists only as a prompt instruction is described as guidance, never as a guarantee.

This plan applies that rule twice: once to decide **what may be marketed**, once to decide **how strongly**. Section 3 is the evidence table; nothing reaches the page without a row in it.

---

## 1. The move: run record → `/how-it-works`

### 1.1 Why it moves rather than dies

The run record is the best asset on the site. It is a real captured production run — sources, four opposed positions, a score matrix with pruned candidates, stress-test survival rates, a cost ledger. No competitor can copy it without having built the same pipeline.

Its problem is **position, not quality**. As a homepage it answers "how does this work?" to a visitor who has not yet asked "why should I care?". Moved one click deep, it becomes the proof page that closes a skeptical technical buyer.

### 1.2 Destination

`/how-it-works` — new route.

`/landing` currently serves a byte-identical copy of the homepage (`ui-next/src/app/landing/page.tsx`), is absent from `sitemap.ts`, and has no canonical pointing home. It is a duplicate-content bug. **Delete it** as part of this move rather than leaving a third copy behind.

### 1.3 Mechanics

The run record is already a clean unit. All five components (`ApparatusToggle`, `RunIndex`, `ScoreMatrix`, `Segments`, plus `demo-record.ts`) live in `components/landing/` and nothing outside that directory imports them.

| Step | Action |
|---|---|
| 1 | `git mv ui-next/src/components/landing/ → ui-next/src/components/run-record/` for the five record components; leave `LandingPage.tsx` behind |
| 2 | Move the record body of `LandingPage.tsx` (lines ~187-491: RunIndex, the five phase Sections, Ledger, Interface) into `components/run-record/RunRecord.tsx` |
| 3 | New `ui-next/src/app/how-it-works/page.tsx` — server component, own `metadata`, renders `SiteHeader` → `RunRecord` → `SiteFooter` |
| 4 | Delete `ui-next/src/app/landing/` |
| 5 | `sitemap.ts`: add `/how-it-works` at priority 0.8, `weekly` |
| 6 | `SiteHeader.tsx` `NAV_LINKS`: insert `How it works → /how-it-works` before Pricing |
| 7 | `SiteFooter.tsx` `LINKS.Product`: add the same |
| 8 | `demo-record.test.ts` moves with the data; no assertions change |

**Preserve on move** (these carry the page's argument and are easy to lose in a refactor):
- the sticky marginal `Section` label with its `§n` mono marker
- semantic HTML: real `<table>` with `<caption>`/`scope`, `<dl>/<dt>/<dd>`, `<ol role="list">`, `<figure>/<figcaption>`
- `scroll-mt-[var(--space-20)]` on every anchored section — `RunIndex` links depend on it
- the two-rounded-shapes rule (rounding means "operable")
- every figure counted from `RUN`, never typed

**Keep the masthead's two lede paragraphs on the homepage**, rewritten. They are the clearest prose on the site and the new page still needs a thesis.

---

## 2. The new homepage: seven capabilities, one spine

### 2.1 The spine

The seven capabilities are not a feature list; they are one claim applied seven ways:

> **Reasoner runs everything past models that disagree, then makes the disagreement part of the output.**

Cross-lab routing is the mechanism behind hallucination mitigation, bias mitigation, the four-image spread, and the multi-perspective methods alike. The page should state the spine once, at the top, then let each capability be an instance of it. That is what stops it reading as a grab-bag.

### 2.2 Section order

Ordered by **strength of evidence**, not by feature glamour. The strongest-backed claim goes first because it also happens to be the most differentiated.

| # | Section | Headline claim | Evidence strength |
|---|---|---|---|
| 1 | **Masthead** | The spine, plus a live figure strip | — |
| 2 | **Hallucination mitigation** | "A model cannot vouch for itself." | **Strongest** — deterministic code rule |
| 3 | **Bias mitigation** | "Scored by models from a different bloc." | **Strong** — numeric penalty + validator + test |
| 4 | **Research grounding** | "It searches like a researcher, not a search box." | **Strong** — real agentic loop, 3 depth tiers |
| 5 | **Reasoning techniques** | "19 named methods. Not 19 prompts." | **Strong** — 36 phase modules, ~100 presets |
| 6 | **Image generation** | "One prompt. Four images. Four labs." | **Strong** — 4 primaries, cross-bloc, SVG family |
| 7 | **Article writing** | "Drafted, fact-checked, audited, re-edited." | **Medium** — real gates, real ceilings (§3.6) |
| 8 | **Brainstorming + coding** | Paired, shorter treatment | **Medium** |
| 9 | **Terms + CTA** | Carried over from current page | — |

### 2.3 Section-by-section content

#### §2 — Hallucination mitigation *(the headline)*

**Claim:** "A model cannot vouch for itself."

**Copy direction:** Most products ask a model whether it is confident. Reasoner does not accept the answer. If a claim's only backing is the model that made it, the label is mechanically downgraded from VERIFIED to HYPOTHESIS — in code, before you see it. VERIFIED requires a non-model source.

**Why this leads:** it is the only claim on the page that is a *deterministic guarantee* rather than a tendency. It is also the exact inverse of what buyers assume AI products do, which makes it memorable.

**Visual:** a two-state diagram — model self-attestation → HYPOTHESIS; search/sensor-backed → VERIFIED. Reuse the `epistemic-verified/-hypothesis/-unknown` classes so the page's own labels demonstrate the system.

**Supporting facts to include:** the three epistemic labels; the post-synthesis verify role in presets; CoVE as a user-selectable method.

#### §3 — Bias mitigation

**Claim:** "Scored by a model from a different bloc."

**Copy direction:** Cross-lab is not enough — two Chinese labs share an ideological prior. Reasoner routes so that the model writing the final answer and the model pruning it never come from the same geopolitical bloc, and so that the generators span at least two. Enforced by a validator and a test, not by intent.

Separately, a dedicated bias sub-agent tags each candidate with typed bias flags and subtracts a severity-weighted penalty from its score. Flagged candidates get pruned on the arithmetic.

**Cite the research.** The invariant is grounded in Buyl et al., npj AI 2026. Naming the paper is a strong trust signal and it is already cited in the code.

**Visual:** reuse `ScoreMatrix`'s bias-flag `†` treatment — a miniature of the real matrix, linking to the full one on `/how-it-works`.

#### §4 — Research grounding

**Claim:** "It searches like a researcher, not a search box."

**Copy direction:** An agentic loop chooses its own next move each iteration: general web, academic sources, discussion platforms, direct page scraping, or your uploaded documents. It goes broad, then narrows. At the deepest tier it plans five or more iterations and cross-references before it will stop.

**Facts:** three depth tiers (speed / balanced / quality); five action types; Brave + Tavily + Perplexity Sonar; document upload search.

**Visual:** the query-refinement progression is the story — show `"Tesla Model Y"` → `"Tesla Model Y Q2 2025 earnings"` → `"Tesla Model Y 2025 production cost breakdown"` as three mono lines. It is concrete, it is real, and it is lifted from the actual prompt.

#### §5 — Advanced reasoning techniques

**Claim:** "19 named methods. Not 19 prompts."

**Copy direction:** Tree-of-Thoughts searches and backtracks. Program-of-Thoughts executes real code in a sandbox. Chain-of-Verification drafts, verifies, then revises. Each is a distinct pipeline, not a different instruction on the same one.

**Facts:** 36 phase modules; ~100 presets across budget/premium tiers; PoT executes in a container sandbox with a 30s wall-clock and 256 MB cap.

**Treatment:** a dense two-column list of method names with one clause each. Density is correct here — the point is *how many* there are. Link each to its docs page.

#### §6 — Image generation

**Claim:** "One prompt. Four images. Four labs."

**Copy direction:** Same thesis as the reasoning engine, applied to pixels. Four models from four different labs generate in parallel — Black Forest Labs, Krea, Sourceful, ByteDance on the budget tier — so one lab's house style, outage, or content refusal can never define your result. Model choice is automatic from prompt intent and measured price, with fallbacks behind every primary.

**Also worth saying:** prompt auto-enhancement; reference-image input; a genuine SVG/vector family that never silently substitutes a raster; five aspect ratios; a 40+ model catalogue.

**Visual:** the four-up grid, obviously — with the lab name under each. This is the page's best pure-visual moment; give it full width.

#### §7 — Article writing

**Claim:** "Drafted, fact-checked, audited, then re-edited."

**Copy direction:** Nine phases. Evidence collection, argument map, draft, fact-check against live sources, structural review, developmental edit, style and copy edit, final audit. If the audit fails, it re-edits and re-audits — automatically, once.

**Also marketable:** a style pass that strips AI-tell phrasing (`delve`, `tapestry`, `pivotal`, and ~60 more banned constructions plus banned sentence openers); a fact-check phase that is a **hard gate** — the run breaks rather than proceeding on a failed check; automatic Sources-section synthesis from the links actually present in the text.

**Honest ceilings — do not oversell (see §3.6):** output is one model call, targeting 800-1200 words. No chaptering, no user-set word target. Say "articles," never "long-form," "books," or "reports."

#### §8 — Brainstorming + coding *(paired, compact)*

**Brainstorming:** ideas generated, semantically deduplicated, clustered, then scored on feasibility / novelty / impact — with novelty explicitly weighted so conventional ideas lose. Verbalized Sampling backs it with an NLI entailment gate for real semantic dedup.

**Coding:** five stages — spec, generate, review, tests, assemble. Code actually runs in a sandbox.

---

## 3. Evidence table

Every headline claim, with its backing and its honest strength. **A claim not in this table does not go on the page.**

| # | Claim | Backing | Strength |
|---|---|---|---|
| 3.1 | Model self-attestation is downgraded VERIFIED → HYPOTHESIS | `application/services/evidence_service.py:19-60` — deterministic `apply_promotion_rules` | **Guarantee.** Code-enforced, no LLM in the loop |
| 3.2 | Epistemic labels on every claim | `domain/models.py` `ClaimLabel`; `.epistemic-*` in `globals.css:981` | **Guarantee** |
| 3.3 | Bias flags reduce a candidate's score numerically | `subagents/critique/hyper_agent.py:139-156` — severity-averaged penalty off a base 10 | **Guarantee.** Arithmetic, not a suggestion |
| 3.4 | Synthesis bloc ≠ scoring bloc; generators span ≥2 blocs | `domain/preset_registry.py:8-16`; `infrastructure/llm/registry.py:579,606` `_VENDOR_BLOC`/`bloc_of`; `scripts/validate_presets.py`; `tests/unit/test_preset_bloc_diversity.py` | **Guarantee.** Validator + test |
| 3.5 | Grounded in published research | Buyl et al., npj AI 2026, cited at `preset_registry.py:8` | **Citable** |
| 3.6 | Agentic research loop, 3 tiers, 5 action types | `phases/_prism.py:4,26,49` — speed / balanced / quality prompts | **Strong.** Loop is code; action choice is the model's |
| 3.7 | Brave + Tavily + Sonar + document search | `infrastructure/search/{brave,tavily}_adapter.py`, `discovery.py`; sonar in preset routing | **Guarantee** |
| 3.8 | 19 methods / 36 phase modules / ~100 presets | `ls src/reasoner/phases/*.py` = 36; `preset_registry.py` = 100 keys | **Guarantee.** Must flow through `capabilities.generated.ts` |
| 3.9 | PoT executes code in a sandbox, 30s / 256 MB | `core/ports/code_executor.py:50-51`; `infrastructure/execution/container_sandbox.py` | **Guarantee** |
| 3.10 | 4 images from 4 different labs, in parallel | `constants_limits.py:458` `IMAGE_GEN_IMAGE_COUNT=4`; `:465` "each primary is a different lab"; `IMAGE_GEN_BUDGET_MODELS` = BFL 🇩🇪 / Krea 🇺🇸 / Sourceful 🇺🇸 / ByteDance 🇨🇳 | **Guarantee** |
| 3.11 | Intent-based model selection; SVG never substituted by raster | `infrastructure/llm/image_model_catalogue.py:211-275` `select_models` + vector EXEMPTION | **Guarantee** |
| 3.12 | Article flow = 9 phases with an audit retry | `application/flows/article.py:137-149`, `:203-236` | **Guarantee** |
| 3.13 | Fact-check is a hard gate | `application/flows/writing.py:36,51-53` — `critical=True` breaks the loop | **Guarantee** |
| 3.14 | Sources section auto-synthesized from real links | `application/flows/writing_phases.py:205-214` — regex extraction | **Guarantee** |
| 3.15 | AI-tell phrasing suppressed | `phases/_shared.py:149-209` `HUMANIZATION_RULES` | **Guidance only.** Prompt text, nothing enforces it. Not applied to the article flow. Word as "steers away from," never "removes" |
| 3.16 | Ideas deduplicated, clustered, scored on novelty | `phases/brainstorming.py:32-48`; `phases/vs_generation.py` NLI entailment gate | **Strong** |
| 3.17 | Coding = spec → generate → review → tests → assemble | `phases/coding.py:64,102,159,221,271` | **Guarantee** |

### 3.x — Claims that must NOT appear

| Claim | Why |
|---|---|
| **AI watermark removal** | **Does not exist.** Zero hits for `watermark` in `src/` or `ui-next/`. No logit analysis, no token-distribution detection, no detector-evasion loop. Nothing to market. See §5.1 |
| "Undetectable AI" / "bypasses AI detectors" | Same — no implementation, and see §5.1 for why it should stay off even if built |
| "Long-form" / "book-length" / "reports" | Single model call, 800-1200 word target (`phases/article.py:132`). No chaptering |
| Author/publication style control | `style_brief` is read in 5 places and injects real prompt text but is **never populated at runtime** — no API field, no UI. Tests set it directly, so they pass while the feature is unreachable |
| SEO optimization | Absent. The only SEO references are search-query formulation in `_prism.py` |
| Configurable tone / audience | Audience hardcoded "sophisticated general audience" (`article.py:58`); tone fixed per method |
| Claim-support ratio enforcement | `ARTICLE_MIN_CLAIM_SUPPORT_RATIO=0.5` is checked at `article_phases.py:179-181` but **only logs** — never gates or retries |

---

## 4. Sequencing

| Phase | Work | Depends on |
|---|---|---|
| **A** | Move run record → `/how-it-works`; delete `/landing`; nav, footer, sitemap | — |
| **B** | Extend `scripts/update_mindmap_meta.py` → emit `imageModelsPerRun`, `imageCatalogueSize`, `searchProviders`, `phaseModules` into `capabilities.generated.ts`; extend `tests/test_site_capabilities_sync.py` | — |
| **C** | New `LandingPage.tsx`: masthead + §2 hallucination + §3 bias | B |
| **D** | §4 research + §5 reasoning techniques | B, C |
| **E** | §6 image generation (four-up visual — needs 4 real captured images, see §5.2) | C |
| **F** | §7 article + §8 brainstorming/coding | C |
| **G** | Extend `claims.test.ts` forbidden list with §3.x phrases; full `tsc`; live verification | all |

**A is independently shippable.** If the rest stalls, the run record is still correctly placed and the duplicate route is still gone.

---

## 5. Open decisions

### 5.1 — Watermark removal *(needs your call)*

The feature does not exist, so there is nothing to move to the page today. If the intent is to **build** it, I'd push back before writing any code:

- Anthropic, OpenAI, and Google all prohibit circumventing provenance measures. Reasoner routes through all three. This risks access across every lab simultaneously.
- It inverts the product's own thesis. A page that says "we tell you exactly what to trust" next to "we make AI text undetectable" reads as a company that does not believe its first claim.

**Recommendation:** market the honest version — "prose that does not read like an LLM wrote it" — which the code already partly supports (3.15) and which sells to the same buyer.

**Related, and worth doing regardless:** the *better* implementation of that feature already exists and is dead. `WRITING_HUMANIZE_SYSTEM` / `writing_humanize_prompt` (`phases/writing.py:426-483`) do a real two-step audit-then-rewrite of AI tells and emit structured `ai_tells` output. Zero call sites. Orphaned consumers still point at it in `services/serializers.py:823-835`, `quality/criteria.py:196-204`, `constants_limits.py:407`, `api/phase_executor.py:50`, plus a stale test calling a deleted method. Reviving it into `ArticleFlow` is a small, high-leverage change that would upgrade 3.15 from *guidance* to *guarantee* — and would make the claim genuinely strong. **Recommend a separate task.**

### 5.2 — Four real images for §6

The four-up grid must show four genuinely generated images from the four real models, not stock or placeholders — same standard as the run record. That means one real paid image run (~cents). **Assumed yes** unless you say otherwise, consistent with the earlier real-pipeline authorization.

### 5.3 — `num_images` default mismatch *(likely a bug)*

`generate_images()` defaults to 4 (`image_generation.py:887`) but the HTTP schema defaults to 2 (`api/schemas.py:203`). So the API ships half the designed spread, and the marketing claim "four images" would be false for any direct API caller who omits the field. Fix the schema default to 4 before the page claims it, or soften the claim to "up to four."

### 5.4 — Carried over, still open from the prior plan

D-3 legal entity/address · D-4 retention SLA · D-6 repo rename/publish. None block this work.
