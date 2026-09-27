# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two confirmed audiences, both reaching Reasoner with a question whose answer carries a
cost if it is wrong.

- **Teams adopting it for consequential decisions.** They arrive through the pricing,
  dashboard, billing and credits surfaces. Their job is to get a defensible answer they
  can put in front of other people, and to see what it cost.
- **Individual power users.** They already have a chatbot and want something better than
  it for hard problems, and will pay per run to get it.

Developers consuming the HTTP API, MCP server or TypeScript SDK exist as a surface
(`docs/`, `developers/`, `capabilities/`, `src/reasoner/api/mcp/`, `sdk/typescript/`)
but were not confirmed as a primary audience. Treat them as secondary until stated
otherwise.

## Product Purpose

Reasoner takes one hard problem and runs it through a structured multi-phase pipeline
instead of answering it in a single pass: classify, decompose, generate perspectives in
parallel across models from different labs, critique and prune, stress-test, then
synthesize. The output separates what is established from what is not, and ends in an
action blueprint.

Success is an answer the user can act on and defend, with the uncertain parts marked as
uncertain rather than smoothed over.

## Positioning

Four claims, all structural rather than promotional, and all verifiable in this
repository:

1. **Cross-lab model diversity.** Phase 2 generates perspectives from at least three
   different labs on Budget presets and four on Premium, and the scorer is forced out of
   the dominant generator's ecosystem. Presets additionally enforce geopolitical-bloc
   diversity. This is enforced by a validator and a test, not by prompt wording.
2. **Epistemic labeling.** Synthesis splits its output into VERIFIED, HYPOTHESIS and
   UNKNOWN, plus an action blueprint. The product does not present a guess as a fact.
3. **Named reasoning methods, auto-routed.** 24 distinct methods across 49 presets,
   including Debate, Jury, Bayesian, Pre-Mortem, Tree-of-Thoughts, Chain-of-Verification
   and Delphi. HyperGate selects one per problem from five sub-agents running in
   parallel, so the user does not have to know which method their question wants.
4. **Propagation resistance.** Recalled memory never enters a system prompt, phase-2
   generators are blind to each other, every phase system prompt is hardened, and
   model-authored or web-authored text is wrapped rather than interpolated. Recorded in
   `docs/MIND_VIRUS_MITIGATION.md` and held by `tests/test_mind_virus_resistance.py`.

## Operating Context

- **Web app.** Chat with SSE streaming, a run dashboard, settings, conversation history
  in IndexedDB. Under `ui-next/`.
- **Marketing and reference surfaces.** Landing, pricing, docs, FAQ, changelog, status,
  security, help, plus legal pages and `llms.txt`.
- **Programmatic access.** HTTP API with roughly 30 endpoints, an optional MCP server,
  and a TypeScript SDK.
- **CLI.** `main.py` for headless runs, preset listing, state save and resume.
- Runs are metered and billed against credits, with spend ceilings.

## Capabilities and Constraints

Confirmed from source on 2026-09-06, not from documentation:

- 216 models in `_MODEL_WHITELIST`, routed directly or through OpenRouter.
- 49 presets, each method offered in a Budget and a Premium tier. The UI orders Budget
  before Premium and defaults to the cheapest.
- 24 reasoning methods.
- Every request passes HyperGate first, which routes to DIRECT, WEB_SEARCH or PIPELINE.
  Real method names are never shown to the routing models; only opaque letters.
- Long-term memory across three cache tiers with embedding search.
- Python 3.12 and FastAPI on the backend; Next.js 16, React 19, TypeScript 5 and
  Tailwind CSS v4 on the frontend. Tailwind v4 declares its theme in
  `ui-next/src/app/globals.css`; there is no `tailwind.config.ts` and there must not be.
- Local development runs against the dev server. A production build blocks the localhost
  backend through its SSRF guard.

**Undecided and not to be invented:** pricing figures, plan names and limits, launch
date, availability commitments, uptime or latency numbers.

## Brand Commitments

- The product name is **Reasoner**.
- Visual authority is `spec/art-direction.md` and `ui-next/src/styles/tokens.css`.
  No raw colour, font-size, spacing or radius value may appear in `ui-next/src/**`
  component code; every value comes from the token file.
- `spec/banlist.md` is binding on every visual decision.
- **`docs/DESIGN.md` is not this product's design system.** It documents ElevenLabs and
  is reference material only. Nothing in it governs Reasoner.
- Hue is a data channel, spent on epistemic status and on danger. `--accent` is
  achromatic by decision, not by omission.
- Claims are labeled VERIFIED, INFERENCE, HYPOTHESIS or UNKNOWN. Anything not verifiable
  in this repository is written as `[INPUT REQUIRED: <question>]` rather than guessed.

## Evidence on Hand

**Nothing is public yet.** There are no users to cite, no benchmarks cleared for
publication, no testimonials, no customer logos, no press, no funding announcement and
no case studies.

Every proof slot on a marketing surface is `[INPUT REQUIRED]` until the owner supplies a
real one. Do not estimate, do not use a placeholder that reads as real, and do not reach
for category-standard filler such as "trusted by teams" or an invented percentage.

The one thing that can be demonstrated honestly is the product's own behavior: a real
run, its phases, its model routing, and its epistemic labels.

## Product Principles

1. **Uncertainty is shown, not smoothed.** The epistemic split is the product. Any
   surface that presents output as uniformly confident contradicts it.
2. **Diversity is structural.** Cross-lab and cross-bloc routing is enforced in code.
   Design must not imply a single house model.
3. **Cost is visible.** Budget and Premium tiers, credits and spend ceilings are real
   product facts. The cheapest option is the default and stays legible as such.
4. **Nothing is fabricated.** Applies to model output and to marketing copy equally. An
   empty proof slot is correct; an invented one is a defect.
5. **The method is chosen for the user.** HyperGate exists so the user does not need the
   vocabulary. Surfacing 24 method names as a required choice would undo it.

## Accessibility & Inclusion

WCAG 2.2 AA. Responsive from 320px. Visible keyboard focus. `prefers-reduced-motion`
respected. Semantic landmarks and real alt text. These are a floor, not a goal, and are
never announced in copy.
