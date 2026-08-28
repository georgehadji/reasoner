/**
 * Documentation content registry.
 *
 * Docs are plain data rather than MDX so that every page is a static server
 * component: the full prose ships in the first HTML response, which is what
 * makes the docs readable by search crawlers and by AI answer engines that do
 * not execute JavaScript.
 */

import { CAPABILITIES } from './capabilities.generated';

export interface DocPage {
  slug: string;
  title: string;
  /** Meta description and card subtitle. Keep under ~155 characters. */
  description: string;
  section: DocSection;
  /** Reading-time hint, in minutes. */
  minutes: number;
  /** Surfaced as article keywords and used by the docs search filter. */
  keywords: string[];
  /** Markdown body, rendered server-side. */
  body: string;
}

export type DocSection =
  | 'Getting started'
  | 'Reasoning'
  | 'Generation'
  | 'Billing'
  | 'Developers'
  | 'Operations';

export const DOC_SECTIONS: DocSection[] = [
  'Getting started',
  'Reasoning',
  'Generation',
  'Billing',
  'Developers',
  'Operations',
];

export const DOCS: DocPage[] = [
  {
    slug: 'quickstart',
    title: 'Quickstart',
    description:
      'Run your first Reasoner pipeline in under a minute, and understand what each phase of the answer is doing.',
    section: 'Getting started',
    minutes: 4,
    keywords: ['quickstart', 'getting started', 'first query', 'tutorial'],
    body: `
## Run your first query

1. Open the [app](/chat).
2. Type a question that has more than one defensible answer — Reasoner is built for judgement calls, not lookups.
3. Press **Enter**. Leave the preset on **Auto** for now.

That is the whole flow. Everything below explains what happened.

## What happens after you press Enter

Every request first passes through **HyperGate**, a pre-router that decides how much machinery your question actually needs. Five classifiers run in parallel — language, complexity, directness, web-search need, and method fit — and a tie-breaker picks one of three outcomes:

| Route | When it fires | Latency |
| --- | --- | --- |
| **Direct** | Simple factual or conversational input | ~1s |
| **Web search** | The answer depends on current information | ~3–8s |
| **Pipeline** | Genuine reasoning work, method auto-selected | ~20–90s |

Only the third route runs the full pipeline. You are not billed for reasoning you did not need.

## The six phases

When a full pipeline runs, the answer is built in stages, and you can watch each one arrive:

- **Phase 0 — Classification.** Identifies the task type and the language to answer in.
- **Phase 1 — Decomposition.** Splits the problem into at most five sub-problems and names the ways an answer could fail.
- **Phase 2 — Generation.** Several models from *different* labs attack the problem in parallel, from constructive, destructive, systemic, and minimalist angles.
- **Phase 3 — Critique.** A separate model scores each candidate 0–10 and prunes the weak ones. The scorer is deliberately from a different ecosystem than the generators.
- **Phase 4 — Stress testing.** Survivors are pushed through optimal, constraint-violating, and adversarial scenarios.
- **Phase 5 — Synthesis.** The result is assembled and every claim is labelled.

## Reading the epistemic labels

The synthesis marks each claim so you know what you are trusting:

- **VERIFIED** — supported by a cited source or an internally consistent derivation.
- **HYPOTHESIS** — plausible and reasoned, but not established.
- **UNKNOWN** — the models could not resolve it, and say so instead of guessing.

Treating "we don't know" as a first-class output is the point. A confident answer that hides its uncertainty is worse than a hedged one that shows it.

## Where to go next

- [Reasoning methods](/docs/reasoning-methods) — what each of the 19 methods is good at.
- [Presets and models](/docs/presets-and-models) — controlling cost and depth.
- [Article generation](/docs/article-generation) — sourced, fact-checked long-form writing.
- [Code generation](/docs/code-generation) — spec, generate, security-review, test.
- [Image generation](/docs/image-generation) — prompts to pictures, outside the pipeline.
- [Credits](/docs/credits) — how usage is metered.
`,
  },
  {
    slug: 'reasoning-methods',
    title: 'Reasoning methods',
    description:
      'The 19 reasoning methods Reasoner can run, what problem shape each one suits, and how to pick between them.',
    section: 'Reasoning',
    minutes: 8,
    keywords: ['methods', 'debate', 'jury', 'bayesian', 'tree of thoughts', 'reasoning'],
    body: `
Reasoner is not one prompt chain. It is 19 distinct reasoning structures, each with its own phases, prompts, and model routing. HyperGate picks one automatically, or you can force a method by choosing a preset.

## Choosing a method

The fastest way to choose: name the shape of your problem.

| Your problem looks like | Use |
| --- | --- |
| "Which of these options should we pick?" | Multi-perspective, Debate |
| "Is this claim true?" | CoVE, Scientific, Jury |
| "What is happening right now?" | Research |
| "Why did this go wrong?" | Pre-mortem, Socratic |
| "How likely is this?" | Bayesian, Delphi |
| "I need a novel angle" | Analogical, Dialectical, Brainstorming |
| "Compute or simulate something" | Program-of-Thoughts |
| "Write something long-form" | Writing |

## The methods

### Multi-perspective (default)
Four viewpoints — constructive, destructive, systemic, minimalist — generated in parallel by models from different labs, then critiqued and stress-tested. The general-purpose choice when you do not know which method fits.

### Debate
An adversarial structure: opening arguments, rebuttals, then an independent judge. Best when the disagreement itself is the information you want.

### Jury
An expert panel of generator, critic, and verifier roles voting on a verdict. Stronger than Debate when the question has a right answer that is hard to reach rather than two legitimate sides.

### Research
Web-grounded iterative retrieval. Searches, reads, identifies gaps, searches again, and synthesises with citations. The only method that reliably handles "as of today".

### Scientific
Generates hypotheses and then actively tries to falsify them. Use when a confident-sounding wrong answer would be expensive.

### Socratic
Elenchus questioning that surfaces the assumptions underneath your question. Frequently reveals that the question needs rewriting.

### Pre-mortem
Assumes the plan has already failed, then works backwards to find why. Excellent for risk review before committing.

### Bayesian
Explicit priors, likelihoods, and posteriors, with a sensitivity pass showing which assumption is load-bearing.

### Dialectical
Thesis, antithesis, and a synthesis that must resolve the specific contradiction rather than average the two.

### Analogical
Maps your problem onto a structurally similar problem in a distant domain and transfers the solution back. Good for breaking fixed framing.

### Delphi
Multiple rounds of independent expert estimates with feedback between rounds, and dissent preserved rather than averaged away.

### Chain-of-Verification (CoVE)
Drafts an answer, generates verification questions against its own claims, answers those independently, then revises. The strongest anti-hallucination structure available.

### Skeleton-of-Thought (SoT)
Outlines first, then expands each section in parallel. Much faster than sequential generation for structured output.

### Tree-of-Thoughts (ToT)
Explores branching reasoning paths, evaluates them, and backtracks from dead ends.

### Program-of-Thoughts (PoT)
Writes and executes code as the reasoning step, so arithmetic and simulation are actually computed rather than predicted.

### Self-Discover
Composes a bespoke reasoning structure for your specific problem out of atomic reasoning modules.

### Writing
Long-form composition with retrieval, claim extraction, adversarial verification, and a journal-style review pass before assembly.

### Brainstorming
Divergent generation, clustering, then development of the most promising clusters.

### Coding
Code-focused structured reasoning with explicit attention to failure modes and edge cases.

## Why models come from different labs

Phase 2 requires at least three different labs on Budget presets and at least four on Premium, and the Phase 3 scorer must come from a different ecosystem than the dominant generator.

This is not vendor neutrality theatre. Models trained on overlapping data with overlapping methods share failure modes: ask five instances of one model family and you get one opinion repeated five times, with the agreement misread as confidence. Enforcing cross-lab spread is what makes the critique phase capable of catching anything.
`,
  },
  {
    slug: 'presets-and-models',
    title: 'Presets and models',
    description:
      `How the ${CAPABILITIES.presets} presets map to reasoning methods, what Budget and Premium change, and how model routing and fallbacks work.`,
    section: 'Reasoning',
    minutes: 6,
    keywords: ['presets', 'models', 'budget', 'premium', 'routing', 'fallback', 'openrouter'],
    body: `
## Presets

A preset is a method plus its model routing. Every method ships in two tiers:

| Tier | Typical cost per run | What changes |
| --- | --- | --- |
| **Budget** | ~$0.02 | Fewer, cheaper models; at least 3 labs in generation |
| **Premium** | ~$0.15–$0.30 | Frontier models; at least 4 labs; more stress-test scenarios |

There are ${CAPABILITIES.presets} presets in total. The picker lists them cheapest-first and defaults to the cheapest option, so cost is opt-in rather than opt-out.

Leaving the preset on **Auto** lets HyperGate pick both the method and the tier from the problem itself.

## Models

Reasoner routes across ${CAPABILITIES.directModels} directly registered reasoning models and ${CAPABILITIES.routableModels}+ more through OpenRouter, spanning ${CAPABILITIES.providerAdapters} model labs including Anthropic, OpenAI, Google, DeepSeek, Mistral, xAI, and Perplexity.

Routing is by **role**, not by preference. Each phase requests a role — generator, scorer, synthesiser, searcher — and the router resolves it against the preset's routing table.

## Fallbacks

When a provider fails, times out, or trips its circuit breaker, the router falls back to a **cross-lab equivalent**, never to the preset's primary model. A blind fallback to the primary would quietly collapse the diversity guarantee at exactly the moment things are going wrong, which is when you can least afford it.

Circuit breakers are per-provider. A provider that keeps failing is skipped entirely until it recovers, rather than being retried on every phase.

## Estimating cost before you run

\`POST /api/estimate\` returns a projected token and cost range for a given problem and preset. The composer calls it as you type, which is where the cost figure next to the run button comes from.
`,
  },
  {
    slug: 'image-generation',
    title: 'Image generation',
    description:
      'Generate images from a prompt: automatic prompt enhancement, several models in parallel across vendors, reference images, and policy-safe retries.',
    section: 'Generation',
    minutes: 5,
    keywords: ['image', 'image generation', 'prompt enhancement', 'reference images', 'flux', 'gemini'],
    body: `
Image generation runs outside the reasoning pipeline. No phases, no critique, no epistemic labels — a prompt goes in and pictures come back.

## Generating an image

In the [app](/chat), press the image toggle in the composer, describe what you want, and press **Enter**. The placeholder changes to *"Describe the image you want to generate…"* when the mode is live.

Two calls happen, in order:

1. **Enhancement.** A fast text model expands your description into a full generation prompt — subject, style, composition, lighting, colour palette, and texture. The expanded prompt is shown in the chat *before* anything is drawn, so you always see what was actually sent.
2. **Generation.** Four models from four different labs run in parallel on that prompt. You get every image that came back, each labelled with the lab that produced it.

Enhancement is on by default because short prompts underspecify everything except the subject, and image models fill those gaps with their own house style. Send \`enhance: false\` when you have already written a full prompt and want it used verbatim.

## Which models run

Model choice follows the tier, and always spans more than one vendor:

Labs rather than model ids: the tiers are re-ranked whenever measured prices move, so a model name here would be stale within the week. The rule that holds is one model per lab, and a bloc boundary crossed in both tiers.

| Tier | Runs in parallel | Falls back to |
| --- | --- | --- |
| **Budget** | Black Forest Labs, Krea, Sourceful, Alibaba | xAI, OpenAI, ByteDance, Recraft, Google |
| **Premium** | OpenAI, Google, Black Forest Labs, ByteDance | Recraft, Microsoft, Sourceful, Krea, OpenAI |

The primaries fire concurrently. If fewer images come back than you asked for, fallbacks are tried one at a time until the count is met or the list runs out. A model that fails does not fail the request — you get what the survivors produced.

The app asks for four images on Budget and two on Premium.

## Policy rewrites

Image providers moderate aggressively, and a moderated request usually arrives as prose rather than as an error you can act on.

So when the models return text instead of an image, or refuse outright, Reasoner rewrites the prompt and retries: named franchises, studios, and mascot characters are replaced with original descriptions that preserve the scene, medium, mood, composition, and palette. If the rewriting model is itself unavailable, a local pattern-based rewrite is the last resort.

When this happens the response carries a \`rewritten_prompt\`. That field is the honest answer to *"why does this not look like what I asked for"* — the prompt changed, and this is exactly how.

## Reference images

Attach up to **four** images to steer style, character, or composition.

Attaching any switches routing to a fixed set of Google and OpenAI models, so a reference-image run draws from a smaller pool than the table above.

Reference images must be \`data:image/...\` URLs. A link to a file on the internet is rejected.

## What you get back

Images are returned as base64 data URLs, never as links to a provider's CDN. When a model responds with a remote URL, the server downloads it — through the same validator that blocks private-network addresses — and inlines the bytes before replying.

That costs a round trip, and it is worth it: provider image URLs expire, often within the hour, and a history entry that renders a broken image a week later is worse than no history at all.

## API

\`\`\`bash
curl -X POST https://reasoner.app/api/generate-image \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "a lighthouse in a winter storm",
    "preset": "image-gen-budget",
    "aspect_ratio": "16:9",
    "num_images": 2
  }'
\`\`\`

| Field | Default | Notes |
| --- | --- | --- |
| \`prompt\` | — | Required. Over 4,000 characters is truncated, not rejected |
| \`preset\` | \`image-gen-budget\` | Or \`image-gen-premium\` |
| \`aspect_ratio\` | \`1:1\` | \`1:1\`, \`16:9\`, \`9:16\`, \`4:3\`, \`3:4\` |
| \`resolution\` | \`1024x1024\` | Clamped per model where the provider requires it |
| \`enhance\` | \`true\` | Set false to send the prompt verbatim |
| \`preview_only\` | \`false\` | Returns the enhanced prompt without generating |
| \`reference_images\` | \`[]\` | Up to 4 image data URLs |
| \`num_images\` | \`2\` | How many images must succeed. 1–8; SVG prompts return fewer, never raster |

\`preview_only\` is what the app uses to show you the enhanced prompt while the images are still rendering — it is a cheap text call, not a generation.

The response is \`{ success, images: [{ image_data, model_used }], enhanced_prompt, rewritten_prompt }\`. On total failure, \`success\` is false and \`error\` names each model that failed and why.

## Limits

| Limit | Value |
| --- | --- |
| Prompt length | 4,000 characters |
| Reference images | 4 |
| Per-model timeout | 90 seconds |
| Remote image fetch | 20 seconds |

Requests are rate-limited per account — per IP and user-agent when signed out — and count against your plan quota. Browser calls need a CSRF token; API-key calls do not.
`,
  },
  {
    slug: 'article-generation',
    title: 'Article generation',
    description:
      'The research-backed editorial pipeline: sourcing, argument map, draft, fact-check with a claim ledger, adversarial review, editing, and a pre-publication audit.',
    section: 'Generation',
    minutes: 7,
    keywords: ['article', 'essay', 'writing', 'long-form', 'fact check', 'claim ledger', 'editorial'],
    body: `
Asking a model to "write an article about X" gets you an article-shaped object: confident, fluent, and quietly full of invented citations. Reasoner treats long-form writing as an editorial process instead — sources first, claims tracked individually, and a review pass that can send the draft back.

## Two methods

| Method | Presets | Shape |
| --- | --- | --- |
| **Writing** | \`writing-budget\`, \`writing-premium\` | 6 phases — sourcing, outline, draft, fact-check, assembly, synthesis |
| **Article** | \`article-budget\`, \`article-premium\` | 9 phases — adds an argument map, adversarial structural review, developmental and style editing, and a pre-publication audit |

Writing is the lighter path for a well-scoped piece. Article is the publication-grade one, and costs proportionally more.

## How a request gets here

HyperGate matches writing intent before anything else runs, so *"write an article about the latest EU battery regulations"* routes to the writing pipeline rather than to a plain web search.

Pure creative requests — a poem, a story, a joke, a letter — deliberately do **not** come here. They take the direct fast path, because retrieval and fact-checking add latency and nothing else to a limerick. Ask for sources, research, or citations and the same request becomes research-backed again.

## The article pipeline

| Phase | What it does |
| --- | --- |
| **2 — Evidence collection** | Plans up to five queries, searches, dedupes by URL, and keeps structured metadata (author, date, publisher) per source |
| **2.5 — Argument map / outline** | Builds the structural blueprint: claim hierarchy, section outline, target word count, working title |
| **3 — First draft** | Writes the full piece against the outline and the retrieved sources |
| **4 — Fact check + claim ledger** | Extracts each factual claim and checks it against the sources, recording a verdict per claim |
| **4.5 — Structural review** | A devil's-advocate pass on logic, hidden assumptions, and ignored counterarguments — not facts, not grammar |
| **5 — Developmental edit** | Rewrites argument, evidence, and narrative flow in response to that critique |
| **6 — Style + copy edit** | Two sequential passes: voice and rhythm, then line-level correctness |
| **7 — Final audit** | A structured pre-publication checklist producing a pass/fail and a score |
| **8 — Synthesis** | Assembles the final output with epistemic labels |

Separating the structural review from the fact check is the load-bearing decision. A model asked to check "everything at once" reliably fixes commas and misses that the second section assumes the conclusion. Give one pass only the claims and another only the argument, and both get harder to fake.

## When the audit fails

If the final audit does not pass, the pipeline runs the developmental edit, the style and copy edit, and the audit again — **once**. One retry, not a loop: a piece that fails twice has a problem editing cannot fix, and burning ten passes on it would cost real money to arrive at the same place.

The retry is skipped when the style edit already timed out on the first pass, since re-running a phase that just failed on latency only stacks up more failures.

## Evidence and claim rules

- Target source count is **8–16**, with roughly six results per query.
- When retrieval returns nothing, an **insufficient-evidence** gate is raised rather than letting the draft proceed unsourced.
- The fact-check phase emits a **claim ledger**: every claim, its verdict, and its supporting source.
- If fewer than **50%** of claims are supported, the gaps are recorded explicitly and carried forward rather than silently smoothed over.

## Model routing

Retrieval and fact-checking route to Perplexity Sonar models, which search the live web natively and return real citations — when Sonar answers, the inline \`[title](url)\` citations are parsed straight out of the response instead of being re-derived.

Drafting routes to long-context prose models, the critic routes to a *different* geopolitical bloc than the drafter, and synthesis routes to a million-token-context model so the whole article fits in one pass rather than being summarised into itself.

## What you get

Markdown, plus the working artefacts: the claim ledger, the structural critique with its rigour score, the editorial audit with its score and pass/fail, and the source list with metadata.

## Experimental: adapter pipeline

Setting \`ARTICLE_USE_ADAPTERS=1\` swaps in an 11-phase variant that adds **Gap Retrieval** (a second search targeted at the claims the fact-check could not support) and **Surface Signals**, with explicit budget guards per phase. It is off by default and is a self-hosting option, not a user-facing setting.
`,
  },
  {
    slug: 'code-generation',
    title: 'Code generation',
    description:
      'The coding pipeline: library research, spec, parallel file generation, CVE-informed security review, test generation, and assembly into a runnable project.',
    section: 'Generation',
    minutes: 6,
    keywords: ['code', 'coding', 'code generation', 'security review', 'tests', 'cve', 'spec'],
    body: `
The coding pipeline produces a project, not a snippet: a spec, one file per unit of work, a security review informed by real vulnerability data, a test suite, and a README of what it does and where it falls short.

Presets are \`coding-budget\` and \`coding-premium\`. HyperGate routes here when the request is to build software — as opposed to *compute* something, which routes to Program-of-Thoughts instead.

## The phases

| Phase | What it does |
| --- | --- |
| **1.5 — Library research** | Searches code-oriented sources for library docs and API references for the stack in question |
| **2 — Spec analysis** | Produces the spec: language, framework, the list of files to generate, and optionally a plan contract with validation commands |
| **3 — Code generation** | One model call per file, in parallel |
| **3.4 — CVE search** | Looks up known vulnerabilities, OWASP guidance, and secure-coding rules for the spec's language and framework |
| **3.5 — Security review** | Adversarial review of the generated code against those findings — **critical**: if it fails, the run stops |
| **4 — Test generation** | Writes a test suite against the generated files |
| **5 — Final assembly** | Consolidates files, applies fixes, and writes the README and known limitations |

Doing the library and CVE searches *before* review, rather than trusting the model's memory of which versions are vulnerable, is the whole point of those two phases. Training data ages; CVE feeds do not.

## Generation is per-file and capped

Each file in the spec gets its own model call, so a ten-file project is ten focused prompts rather than one prompt asked to hold the entire codebase in its head.

Concurrency is capped at **four** simultaneous calls. Fourteen parallel calls to a frontier model reliably trips rate limits, and a 429 halfway through generation is more expensive than running slightly slower.

Three guardrails apply to every generated file:

- **The path is enforced by the spec.** A model cannot rename or relocate its own file.
- **Parse failures degrade, they do not delete.** If a model returns raw code where JSON was requested, the raw output becomes the file content rather than being discarded.
- **Reasoning tags are stripped** so no \`<think>\` block ever lands in shipped source.

If the spec produces no files at all, a single-file fallback spec is synthesised so the request still returns working code.

## Contract validation

When the spec emits a plan contract with validation commands and a code executor is available, those commands are actually run and the exit code is attached to the result as execution evidence.

This is the difference between "the model believes this compiles" and "this compiled". Where the environment supports it, take the evidence over the belief.

## Why there is no synthesis phase

Every other method ends with a synthesis pass. Coding ends at assembly, deliberately.

A synthesis prompt would have to include the full content of every generated file — roughly 100k tokens for a typical project — which overflows the context window of all but a handful of models, to produce a paragraph describing files you already have. Assembly *is* the synthesis here, and the final result is populated directly from it.

For the same reason, the final output carries the README plus a file **index** with line counts, not the file bodies inline. The code itself lives in the run's file list, where it can be read or downloaded without being duplicated through the context window twice.

## Model routing

Budget routes generation to a dedicated coding model rather than a general-purpose cheap model — code-specialised models at that price are meaningfully better at code and fast enough for the phase budget. Premium routes the spec and generation to a frontier model, with review, tests, and assembly on cross-lab models so the reviewer is never marking its own homework.

Reasoning models that emit output on a separate channel are deliberately excluded from coding roles: they leave the content field empty, which reads downstream as a file that generated nothing.

## What you get

The generated files, a test suite, a README, the list of fixes applied during assembly, and an explicit **known limitations** list.

Read the limitations list. Nothing here is executed beyond the contract validation commands, so the code is reviewed and tested-on-paper rather than proven to run. Treat it as a strong first draft from someone who read the CVE feed — not as merge-ready output.
`,
  },
  {
    slug: 'credits',
    title: 'Credits',
    description:
      'How Reasoner meters usage: what a credit is worth, when you are charged, monthly allowances, and how to read your ledger.',
    section: 'Billing',
    minutes: 5,
    keywords: ['credits', 'billing', 'usage', 'ledger', 'quota', 'pricing'],
    body: `
## What a credit is

**1,000 credits = $1.00** of underlying model spend. One credit is therefore a tenth of a cent.

Credits are integers. Every charge rounds *up* to the next whole credit, so nothing is ever silently free, and a ledger can never accumulate floating-point drift.

Typical costs:

| Run | Approximate cost |
| --- | --- |
| Direct answer (HyperGate fast path) | 0–2 credits |
| Web search answer | 2–8 credits |
| Budget pipeline | ~20 credits |
| Premium pipeline | ~150–300 credits |

## Monthly allowance

Each subscription tier grants an allowance at the start of every billing period:

| Tier | Credits per month |
| --- | --- |
| Free | 500 |
| Pro | 25,000 |
| Enterprise | 250,000 |

The grant is idempotent per period — checking your balance tops it up if the period has rolled over, and it can never be granted twice for the same month.

## When you are charged

**After the run completes, from actual model spend.** Not on submission, and not from an estimate.

This matters more than it sounds:

- A run that fails before any model is called costs **nothing**.
- A cache hit costs **nothing**.
- You pay the real cost of the models that actually ran, not a padded estimate.

Because settlement happens after the work, a single run can take your balance to zero or slightly below. The next run is then blocked with **402 Payment Required** until you top up. Every charge carries an idempotency key, so a dropped connection or a retried request cannot double-charge you.

## Reading your ledger

The ledger is append-only. Every entry records the amount, the reason, and the resulting balance, so any balance can be audited without replaying the whole history.

Reasons you will see: \`monthly_grant\`, \`purchase\`, \`signup_bonus\`, \`pipeline_run\`, \`image_generation\`, \`web_search\`, \`refund\`, \`admin_adjustment\`.

## API

\`\`\`bash
# Current balance and this period's allowance
curl -H "Authorization: Bearer $REASONER_API_KEY" \\
  https://reasoner.app/api/credits

# Ledger, newest first
curl -H "Authorization: Bearer $REASONER_API_KEY" \\
  "https://reasoner.app/api/credits/ledger?limit=50"
\`\`\`

\`GET /api/credits/pricing\` is public and returns the current conversion rate and tier allowances, so a client can display costs without authenticating.
`,
  },
  {
    slug: 'api-keys',
    title: 'API keys',
    description:
      'Create, scope, rotate, and revoke Reasoner API keys, and how to authenticate programmatic requests safely.',
    section: 'Developers',
    minutes: 5,
    keywords: ['api key', 'authentication', 'bearer token', 'scopes', 'security', 'rotation'],
    body: `
API keys let scripts, agents, and backend services call Reasoner without a browser session.

## Creating a key

Go to [Settings → API keys](/settings/api-keys), name the key after where it will run ("prod-ingest", "laptop"), and choose its scopes.

The plaintext key is shown **once**. Only its SHA-256 hash is stored, so a lost key cannot be recovered — mint a new one and revoke the old.

Keys look like:

\`\`\`
rsn_live_kJ8xQ2mNp4vR7wT1yU3bE5hG6jK9lM0n...
\`\`\`

## Using a key

Send it as a bearer token:

\`\`\`bash
curl -X POST https://reasoner.app/api/run \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "Should we migrate off our monolith?", "preset": "auto-budget"}'
\`\`\`

Key-authenticated requests do not need a CSRF token. CSRF exists to stop a malicious page from replaying a browser's ambient credentials; a page cannot attach your secret key to an \`Authorization\` header, so the attack it defends against does not apply.

## Scopes

A key can only be granted scopes its owner already has, and administrative scopes are never assignable to user keys — a key can never escalate beyond the account behind it.

| Scope | Grants |
| --- | --- |
| \`read\` | Run pipelines, read results |
| \`write\` | Modify settings, clear cache |
| \`preset:read\` | List presets and models |
| \`history:read\` | Read run history |
| \`history:delete\` | Delete history entries |

New keys default to read-only (\`read\`, \`preset:read\`, \`history:read\`). Grant more only when something actually needs it.

## Expiry, limits, and rotation

- Keys can be given a lifetime of 1–365 days, or left non-expiring.
- Each account may hold up to **20** live keys.
- Revocation takes effect immediately; the next request with that key returns 401.

Rotate without downtime: mint the new key, deploy it, confirm traffic has moved, then revoke the old one.

## Keeping keys safe

- Store keys in environment variables or a secret manager — never in source control, never in client-side code.
- Give each environment its own key, so revoking one does not take down the others.
- Deleting your account revokes every key it owns.

If a key leaks, revoke it first and investigate second. Your ledger shows exactly what was spent under it.
`,
  },
  {
    slug: 'api-reference',
    title: 'API reference',
    description:
      'HTTP endpoints for running pipelines, streaming results over SSE, estimating cost, and managing credits and keys.',
    section: 'Developers',
    minutes: 9,
    keywords: ['api', 'rest', 'sse', 'streaming', 'endpoints', 'reference', 'http'],
    body: `
Base URL: \`https://reasoner.app\`

All authenticated endpoints take \`Authorization: Bearer <key>\`. Responses are JSON except \`/api/run\`, which streams Server-Sent Events.

## Run a pipeline

\`\`\`http
POST /api/run
Content-Type: application/json
Authorization: Bearer rsn_live_...
\`\`\`

\`\`\`json
{
  "problem": "Should we migrate off our monolith?",
  "preset": "auto-budget",
  "top_k": 2,
  "web_search": false,
  "enhance_prompt": true,
  "client_run_id": "your-idempotency-key"
}
\`\`\`

\`client_run_id\` is both a duplicate-run guard and the credit idempotency key. Reusing one returns **409** rather than running twice, and the run is never charged twice.

The response is an SSE stream:

\`\`\`
data: {"type":"start","preset":"auto-budget","method":"multi-perspective"}
data: {"type":"phase_complete","phase":2,"models":["claude-sonnet","deepseek-v3"]}
data: {"type":"done","total_tokens":{"input":8213,"output":3944,"total":12157},
       "total_cost_usd":0.0191,"duration":41.2,"errors":[]}
\`\`\`

Event types: \`start\`, \`phase_start\`, \`phase_complete\`, \`error\`, \`done\`. Ignore unknown types — new ones are added without a version bump.

Read \`total_cost_usd\` on the \`done\` frame to know exactly what the run cost; that same figure is what is charged against your credits.

## Follow-up in context

\`\`\`http
POST /api/run-followup
\`\`\`

Takes the prior conversation plus a new question and streams the same event shape.

## Estimate before running

\`\`\`http
POST /api/estimate
\`\`\`

Returns a projected token count and USD range for a problem and preset, without running anything.

## Ask the router

\`\`\`http
POST /api/gate
\`\`\`

Returns HyperGate's decision — route, method, and confidence — without executing it. Useful for showing users what will happen before they commit.

## Catalogue

| Endpoint | Returns |
| --- | --- |
| \`GET /api/presets\` | All 48 presets with method, tier, and cost band |
| \`GET /api/models\` | Registered models with vendor and pricing |
| \`GET /api/credits/pricing\` | Credit conversion rate and tier allowances |
| \`GET /api/health\` | Liveness and dependency status |

## Agent endpoints

Bearer-only variants of the run endpoints, built for programmatic callers. See [Agent integration](/docs/agent-integration) for the full guide.

| Endpoint | Returns |
| --- | --- |
| \`POST /api/agent/run/sync\` | One JSON \`RunResult\` once the pipeline finishes |
| \`POST /api/agent/run\` | Same SSE stream as \`/api/run\` |
| \`GET /api/agent/tools\` | Tool definitions (\`?format=anthropic\|openai\`) |

## Credits

| Endpoint | Purpose |
| --- | --- |
| \`GET /api/credits\` | Balance, tier, monthly allowance |
| \`GET /api/credits/ledger?limit=&offset=\` | Ledger, newest first |

## API keys

| Endpoint | Purpose |
| --- | --- |
| \`GET /api/account/api-keys\` | List your keys (never secrets) |
| \`POST /api/account/api-keys\` | Mint a key; plaintext returned once |
| \`DELETE /api/account/api-keys/{id}\` | Revoke a key |

## Errors

| Status | Meaning | What to do |
| --- | --- | --- |
| 400 | Malformed request | Fix the payload; \`detail\` names the field |
| 401 | Missing, invalid, or revoked credentials | Check the key; mint a new one |
| 402 | Credit balance exhausted | Top up, or wait for the monthly grant |
| 403 | Scope or CSRF failure | Grant the scope the call needs |
| 409 | Duplicate \`client_run_id\` | Reuse the original run's result |
| 429 | Rate limited | Back off for \`Retry-After\` seconds |
| 503 | Dependency unavailable | Retry with backoff |

Rate limit headroom is returned on every response as \`X-RateLimit-Limit\` and \`X-RateLimit-Remaining\`.
`,
  },
  {
    slug: 'agent-integration',
    title: 'Agent integration',
    description:
      'Call Reasoner from an autonomous agent: tool definitions, streaming, preset choice, retries, and what to do with labelled claims.',
    section: 'Developers',
    minutes: 8,
    keywords: [
      'agent',
      'tool use',
      'function calling',
      'langchain',
      'claude',
      'openai',
      'autonomous',
      'sdk',
    ],
    body: `
Reasoner is meant to be called by software as readily as by a person. An agent sends one authenticated POST, reads a stream, and gets back a synthesis in which every claim is labelled **VERIFIED**, **HYPOTHESIS**, or **UNKNOWN** — which is what makes the output safe to hand to another model.

## When to delegate to Reasoner

A Reasoner run costs more and takes longer than a single model call. It earns that on questions where one model's confident answer is itself the risk.

| Worth a run | Not worth a run |
| --- | --- |
| "Should we migrate off the monolith this quarter?" | "What is the syntax for a Postgres upsert?" |
| "Which of these three vendors survives our compliance review?" | "Summarise this file." |
| "What breaks if we ship this pricing change?" | Anything the calling model already answers reliably |

If the question has one determinate answer, HyperGate will route it to a Direct reply anyway — you are not billed for reasoning you did not need — but the round trip is still wasted. Filter before you call.

## Authenticate

Use a key from [Settings → API keys](/settings/api-keys) as a bearer token. Key-authenticated requests are exempt from CSRF, so no token-fetch round trip is needed:

\`\`\`http
POST /api/run
Authorization: Bearer rsn_live_...
Content-Type: application/json
\`\`\`

A default read-only key (\`read\`, \`preset:read\`, \`history:read\`) is enough to run pipelines. Give agents nothing more. See [API keys](/docs/api-keys).

## Run it — sync or streamed

Two endpoints, same pipeline, same event contract underneath. Pick whichever matches what your agent can consume.

| Endpoint | Shape | Use when |
| --- | --- | --- |
| \`POST /api/agent/run/sync\` | One JSON \`RunResult\` | Your agent makes one call and reads one response — no SSE parser needed |
| \`POST /api/agent/run\` (or \`/api/run\`) | \`text/event-stream\` | You want per-phase progress, or you are already set up to read SSE |

Both are Bearer-authenticated, both are idempotent on \`client_run_id\`, both settle credits identically — \`/run/sync\` is not a lesser path, it is the streaming pipeline with the collapsing done for you server-side.

\`\`\`bash
curl -s https://reasoner.app/api/agent/run/sync \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "Should we migrate off our monolith?", "preset": "auto-budget"}'
\`\`\`

\`\`\`json
{
  "preset": "auto-budget",
  "method": "multi-perspective",
  "synthesis": "Migrate incrementally, starting with billing.",
  "critical_insights": ["The monolith is not the bottleneck; the deploy pipeline is."],
  "claim_labels": { "The deploy pipeline is the bottleneck": "VERIFIED" },
  "action_blueprint": [{ "step": "1", "action": "Extract billing", "go_criteria": "Deploys independently twice a week" }],
  "citations": [],
  "total_cost_usd": 0.0191,
  "models_used": ["claude-sonnet", "deepseek-v3"],
  "errors": []
}
\`\`\`

### If you stream instead

\`/api/agent/run\` and \`/api/run\` return the identical Server-Sent Events; keep the two frames that matter:

- The **last \`phase_complete\` frame carrying \`data.core_solution\`** — this is the answer, and \`critical_insights\`, \`open_questions\`, \`claim_labels\`, and \`action_blueprint\` sit beside it in the same \`data\` object.
- The terminal **\`done\` frame** — \`total_cost_usd\`, \`total_tokens\`, \`duration\`, \`errors\`.

Citations, when a web-grounded method ran, arrive on their own \`phase_complete\` frame under \`data.citations\`. Ignore event types you do not recognise; new ones are added without a version bump.

\`\`\`python
import json, uuid, httpx

def ask_reasoner(problem: str, api_key: str, preset: str = "auto-budget") -> dict:
    """Run one pipeline and collapse the stream into a result dict.

    Equivalent to calling /api/agent/run/sync — written out so you can see
    what that endpoint does for you, or adapt it if you want progress events
    along the way.
    """
    result = {"synthesis": "", "insights": [], "labels": {}, "cost_usd": 0.0, "errors": []}
    body = {"problem": problem, "preset": preset, "client_run_id": str(uuid.uuid4())}

    with httpx.stream(
        "POST",
        "https://reasoner.app/api/agent/run",
        json=body,
        headers={"Authorization": "Bearer " + api_key},
        timeout=httpx.Timeout(620.0, connect=10.0),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event.get("type") == "phase_complete":
                data = event.get("data") or {}
                if data.get("core_solution"):
                    result["synthesis"] = data["core_solution"]
                    result["insights"] = data.get("critical_insights", [])
                    result["labels"] = data.get("claim_labels", {})
            elif event.get("type") == "done":
                result["cost_usd"] = event.get("total_cost_usd", 0.0)
                result["errors"] = event.get("errors", [])
    return result
\`\`\`

Everything below is about calling either endpoint well.

## Register it as a tool

Fetch the live definition rather than hand-copying one — it is generated from the same request schema the API validates against, so it cannot drift out from under you:

\`\`\`bash
curl -s https://reasoner.app/api/agent/tools
curl -s https://reasoner.app/api/agent/tools?format=openai
\`\`\`

\`format=anthropic\` (the default) returns \`{name, description, input_schema}\` entries ready for Claude's tool-use API; \`format=openai\` returns the same tools wrapped in OpenAI's function-calling shape. The response is cacheable — fetch it once per agent session, not per call. Shape:

\`\`\`json
{
  "name": "reasoner_run_sync",
  "description": "Delegate a judgement call to a panel of models from different labs. They generate competing answers, critique and score each other, stress-test the survivors, and return one synthesis in which every claim is labelled VERIFIED, HYPOTHESIS, or UNKNOWN. Blocking: takes 20-90 seconds and costs real money. Use for decisions with more than one defensible answer; do not use for lookups, syntax, or summarisation.",
  "input_schema": {
    "type": "object",
    "properties": {
      "problem": { "type": "string", "description": "The decision or question, with the constraints that matter." },
      "preset": { "type": "string", "description": "Preset id from reasoner_presets. Omit for auto-budget." }
    },
    "required": ["problem"],
    "additionalProperties": false
  }
}
\`\`\`

The same call also returns \`reasoner_run\`, \`reasoner_gate\`, \`reasoner_estimate\`, \`reasoner_presets\`, and \`reasoner_health\` — register the whole array, not just the run tool; the read-only ones are what let an agent check cost and routing before committing to a paid call.

TypeScript callers can skip the plumbing entirely: the \`@reasoner/sdk\` client exposes \`runToCompletion()\`, which returns \`{ synthesis, criticalInsights, claimLabels, costUsd, modelsUsed }\` already parsed.

## Or skip the HTTP layer: MCP

If your agent host speaks [MCP](https://modelcontextprotocol.io) — Claude Desktop, Claude Code, most current agent frameworks — none of the above is necessary. Reasoner ships an MCP server exposing \`reasoner_run\`, \`reasoner_gate\`, \`reasoner_estimate\`, \`reasoner_presets\`, \`reasoner_health\`, and \`reasoner_followup\` directly as tools, with per-phase progress notifications instead of a stream you parse yourself:

\`\`\`json
{
  "mcpServers": {
    "reasoner": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": { "REASONER_API_KEY": "rsn_live_..." }
    }
  }
}
\`\`\`

A run started this way is billed and idempotency-guarded identically to \`/api/agent/run/sync\` — MCP is a different door onto the same pipeline, not a different product. Full setup, the complete tool reference, and the streamable-HTTP transport are in [MCP server](/docs/mcp).

## Choose the preset deliberately

Leaving \`preset\` unset means \`auto-budget\`: HyperGate picks the method and the Budget tier. That is the right default for an agent. Override it when the caller knows something the router cannot infer — that the question needs live sources (\`research-*\`), adversarial pressure (\`debate-*\`, \`pre-mortem-*\`), or explicit belief updating (\`bayesian-*\`).

Two endpoints let an agent look before it leaps, both taking the same body as \`/api/run\`:

| Endpoint | Returns | Use it to |
| --- | --- | --- |
| \`POST /api/gate\` | \`action\`, \`method\`, \`preset\`, \`confidence\`, \`needs_confirmation\` | See which method would run, without running it |
| \`POST /api/estimate\` | \`estimated_cost_usd\`, token counts, \`estimated_duration_seconds\` | Abort before spending on an over-budget run |

\`/api/gate\` shares HyperGate's cache, so a following \`/api/run\` on the same problem does not re-pay the routing cost. When it returns \`needs_confirmation: true\`, the router is unsure — a good moment for an agent to ask its own caller rather than commit.

\`GET /api/presets\` returns all 48 presets with method, tier, and cost band. Fetch it once and cache it; an agent that hardcodes preset names will break when the catalogue moves.

## Long runs, timeouts, and retries

- A pipeline is capped at **600 seconds**. Set the client timeout above that — 620s is a sane figure — or you will abandon runs you have already paid for.
- Always send a \`client_run_id\`. It is both the duplicate-run guard and the credit idempotency key: re-sending the same id returns **409** instead of running twice.
- If the stream drops mid-run, reconnect with the **same** \`client_run_id\`. Never retry with a fresh one — that is how an agent bills two runs for one question.
- Runs settle **after** completion, from the actual \`total_cost_usd\` on the \`done\` frame. Failed runs cost nothing.

| Status | Agent behaviour |
| --- | --- |
| 402 | Stop. Credits are exhausted; retrying cannot succeed. |
| 409 | Reuse the original run's result. Do not re-run. |
| 429 | Back off for \`Retry-After\` seconds. Watch \`X-RateLimit-Remaining\` and throttle before you hit the wall. |
| 503 | Retry with exponential backoff. |

An \`errors\` array on the \`done\` frame that is non-empty alongside a populated \`core_solution\` means a phase degraded but the run still produced an answer. Treat it as a partial result, not a failure.

## What to do with the answer

The labels are the product. An agent that flattens them back into undifferentiated prose has thrown away the reason it called Reasoner.

- Pass \`claim_labels\` through to whatever consumes the output. A **HYPOTHESIS** presented as fact is worse than no answer.
- \`open_questions\` are the model telling you what it could not settle — good candidates for a follow-up run or a question back to the user.
- \`action_blueprint\` entries are normalised to \`step\`, \`action\`, \`time_horizon\`, \`go_criteria\`, \`fallback\`. The \`go_criteria\` field is what makes a step checkable later.
- To continue the thread, \`POST /api/run-followup\` with the \`conversation_id\`, the prior \`previous_synthesis\`, and the new \`question\`. It streams the same event shape.

## Discovery

An agent that has never seen this API can bootstrap from:

| Resource | Contents |
| --- | --- |
| \`GET /api/agent/tools\` | Tool definitions for the agent-facing endpoints, cacheable |
| \`GET /openapi.json\` | Full OpenAPI schema for every endpoint |
| [\`/llms.txt\`](/llms.txt) | Machine-readable index of this documentation |
| [\`/llms-full.txt\`](/llms-full.txt) | The entire documentation corpus in one file |
| \`GET /api/presets\`, \`GET /api/models\` | Live preset and model catalogues |
| \`GET /api/health\` | Liveness and dependency status |

## Safety notes for agent operators

- Keep the key out of the prompt. An agent that can read its own key can leak it into a transcript.
- Everything sent in \`problem\` is sanitised before it reaches any model, but sanitisation is not authorisation — if your agent forwards untrusted text, it is still forwarding untrusted text.
- Give each agent its own key. Revoking one then costs you one agent, not the fleet, and the ledger attributes spend per key.

## Self-hosted deployments

The endpoints above work identically on a self-hosted instance – same paths, same \`rsn_live_\` account keys, same metering. One addition: with \`ENABLE_LEGACY_API_KEY=true\`, a legacy admin key also authenticates on these paths, for instances mid-migration off the pre-account-key auth system. New deployments should leave that flag off and mint account keys instead.
`,
  },
  {
    slug: 'mcp',
    title: 'MCP server',
    description:
      'Add Reasoner to Claude Desktop, Claude Code, or any MCP host: install, config, the six tools, per-phase progress, and idempotent billing.',
    section: 'Developers',
    minutes: 6,
    keywords: [
      'mcp',
      'model context protocol',
      'claude desktop',
      'claude code',
      'stdio',
      'tools',
      'agent',
      'integration',
    ],
    body: `
Reasoner ships an [MCP](https://modelcontextprotocol.io) server, so any host that speaks Model Context Protocol — Claude Desktop, Claude Code, most current agent frameworks — can call it as a tool provider with no HTTP client code.

It is a driving adapter, the same tier as the REST API. An MCP tool call runs the identical application-layer path as \`POST /api/agent/run\`: same auth resolution, same idempotency guard, same credit metering, same run ownership record. A run started from Claude Desktop is billed exactly like one started from curl.

## Install

The server lives behind an optional extra:

\`\`\`bash
pip install "reasoner[mcp]"
\`\`\`

From a source checkout, \`pip install -e ".[mcp]"\`. If you manage dependencies yourself, the only requirement is \`mcp>=1.2,<2\`.

## Run it over stdio

This is what Claude Desktop and Claude Code use. Add the server to your host's MCP config:

\`\`\`json
{
  "mcpServers": {
    "reasoner": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": { "REASONER_API_KEY": "rsn_live_..." }
    }
  }
}
\`\`\`

Point \`args\` at \`mcp_server.py\` in your checkout — use an absolute path unless you are certain the host's working directory is the repo root. The host launches it as a subprocess and talks to it over stdin and stdout; nothing is exposed on the network.

\`REASONER_API_KEY\` is a normal account key from [Settings → API keys](/settings/api-keys). The two metered tools need it. The four read-only tools work without one, exactly as their unauthenticated HTTP counterparts do.

## Or over streamable HTTP

For a deployment that wants an MCP endpoint without running a second process:

\`\`\`bash
ENABLE_MCP_HTTP=true
\`\`\`

That mounts the MCP server at \`/mcp\` on the same FastAPI app that serves the REST API, authenticated the same way — \`Authorization: Bearer <key>\` on the request. It is off by default; most installs use stdio.

## The tools

| Tool | Cost | What it does |
| --- | --- | --- |
| \`reasoner_run\` | Paid | Runs a reasoning pipeline. Blocks, and reports progress per phase. |
| \`reasoner_followup\` | Paid | Continues a conversation with a prior synthesis as context. |
| \`reasoner_gate\` | Free | Previews routing — direct, web search, or pipeline, and which method — without running it. |
| \`reasoner_estimate\` | Free | Estimates tokens, cost, and duration without running it. |
| \`reasoner_presets\` | Free | Lists presets with method, description, and primary model. |
| \`reasoner_health\` | Free | Liveness and dependency status, public detail only. |

\`reasoner_run\` takes \`problem\` plus optional \`preset\`, \`top_k\`, \`web_search\`, \`source_type\`, and \`client_run_id\`. Leaving \`preset\` unset means \`auto-budget\`: the router picks the method and the cheaper tier, which is the right default for an agent.

Fetch \`reasoner_presets\` once per session and cache it rather than hardcoding preset ids. They are data, and the catalogue moves independently of the tool schema.

There is no admin tool, no key-management tool, and no data-export tool on this surface, and there will not be. That boundary is enforced by a test rather than by convention.

## Progress

A twenty-to-ninety-second tool call that returns nothing until it finishes is a bad experience in a chat host. \`reasoner_run\` and \`reasoner_followup\` emit an MCP progress notification for each \`phase_start\` and \`phase_complete\`, so a host UI can show *Phase 3: Critique* instead of an opaque spinner.

## Idempotency and billing

Pass \`client_run_id\` to make a call retry-safe. Reusing an id that is in flight returns a clean tool error instead of running — and billing — the pipeline a second time. It is the same contract as the REST API's \`client_run_id\`.

Runs settle after they complete, from the run's actual cost. A failed run costs nothing. See [Credits](/docs/credits) for how the metering works.

## What this does not do

- **No per-session concurrency limit.** An agent that fires several \`reasoner_run\` calls back to back can run them concurrently, each billed independently. A standard function-calling loop calls one tool, waits, then decides — so this has not been a problem in practice, but it is assumed rather than enforced. If your loop can call tools without waiting, throttle it yourself.
- **No pinned output schema.** Tool results come back as an MCP structured-content dict derived from the Python return type. The shape matches the REST \`RunResult\` — \`synthesis\`, \`critical_insights\`, \`claim_labels\`, \`action_blueprint\`, \`citations\`, \`total_cost_usd\` — but it is not yet published as a versioned JSON Schema the way the HTTP tool-discovery format is.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Host shows no Reasoner tools | \`mcp\` extra not installed, or \`args\` points at a path the host cannot resolve. Use an absolute path. |
| "No credentials" on \`reasoner_run\` | \`REASONER_API_KEY\` missing from the server's \`env\` block. The free tools keep working without it. |
| A tool error naming a duplicate run | A \`client_run_id\` still in flight. Reuse that run's result; you were not billed twice. |
| Calls fail with 402 | The account's credits are exhausted. Retrying cannot succeed — see [Credits](/docs/credits). |

## See also

- [Agent integration](/docs/agent-integration) — the general guide: when to delegate, retry semantics, and what to do with labelled claims. Most of it applies here.
- [API reference](/docs/api-reference) — the HTTP surface the MCP tools sit on top of.
- [API keys](/docs/api-keys) — scopes, rotation, and revocation.
`,
  },
  {
    slug: 'security-and-privacy',
    title: 'Security and privacy',
    description:
      'How Reasoner handles your data: prompt-injection defence, retention controls, encryption, and GDPR export and deletion.',
    section: 'Operations',
    minutes: 5,
    keywords: ['security', 'privacy', 'gdpr', 'encryption', 'prompt injection', 'retention'],
    body: `
## Input handling

Every piece of user-supplied text is sanitised before it can reach a prompt: HTML and script content stripped, null bytes removed, Unicode NFKC-normalised, and known prompt-injection patterns filtered.

Uploaded documents are treated as untrusted data, never as instructions. Text inside a PDF telling the model to ignore its instructions is content to be reasoned about, not a command to follow.

## Defence in depth

- **Authentication** — OAuth/JWT for browsers, scoped API keys for programmatic access.
- **Authorisation** — per-scope permission checks on every route.
- **Rate limiting** — token-bucket per client, with tier-aware limits.
- **CSRF** — HMAC-SHA256 signed double-submit tokens on browser requests.
- **Circuit breakers** — failing providers are isolated rather than retried into the ground.
- **Headers** — HSTS, CSP, \`X-Frame-Options: DENY\`, \`X-Content-Type-Options: nosniff\`, strict referrer policy.

## Your data

- **Encryption** — AES-256-GCM at rest, TLS 1.3 in transit.
- **Retention** — configurable in [Settings](/settings): keep forever, 30 days, 7 days, or 24 hours.
- **Zero-retention mode** — queries and results are not persisted at all. Use it for sensitive research; note that history and Neuro memory are unavailable for those runs by definition.
- **Neuro memory** — long-term recall is tenant-isolated per account and can be cleared at any time.

## GDPR

- **Export (Article 20)** — \`GET /api/account/export\` returns your profile, subscription, quota, and recent query metadata as JSON.
- **Deletion (Article 17)** — \`POST /api/account/delete\` cancels billing, deletes the database records transactionally, then clears uploads, history, vectors, and cache. API keys are revoked with the account.

Deletion is irreversible. Export first if you want a copy.

## Reporting a vulnerability

Email the security contact listed on [our security page](/security). Please include reproduction steps and give us a reasonable window before public disclosure.
`,
  },
  {
    slug: 'troubleshooting',
    title: 'Troubleshooting',
    description:
      'Fixes for the failures people actually hit: 402s, stalled streams, unexpected methods, and inconsistent answers.',
    section: 'Operations',
    minutes: 5,
    keywords: ['troubleshooting', 'errors', 'debugging', 'support', 'faq'],
    body: `
## "Insufficient credits" (402)

Your balance is exhausted. Because runs settle after they complete, the run that emptied the balance still finished and was charged.

Options: wait for the next monthly grant, upgrade the plan, or top up. Check [your ledger](/dashboard) to see what consumed the balance — a handful of Premium runs will do it faster than expected.

## The stream stops mid-run

Reconnect and re-send with the **same** \`client_run_id\`. The idempotency guard prevents a duplicate run and a duplicate charge.

If it recurs, a provider is likely timing out. Try a Budget preset — it uses fewer models and completes faster.

## It picked a method I did not expect

HyperGate optimises for fitness to the problem, not for spectacle. A question that reads as complex but has a determinate answer will route to Direct, and that is usually correct.

To force a method, select its preset explicitly instead of leaving it on Auto.

## The answer contradicts an earlier one

Check the epistemic labels first. Two **HYPOTHESIS** claims disagreeing is the system reporting genuine uncertainty rather than manufacturing false consensus.

If two **VERIFIED** claims disagree, that is a real bug — please report it with both run IDs.

## Answers feel shallow

Three things to try, in order:

1. Move from Budget to Premium — more models, deeper stress testing.
2. Pick a method that matches your problem shape ([method guide](/docs/reasoning-methods)).
3. Give more context in the prompt. Decomposition can only split what you supplied.

## 401 on a key that worked yesterday

Either the key expired or it was revoked. Expiry is shown in [Settings → API keys](/settings/api-keys). Revocation is immediate and permanent — mint a replacement.

## 429 rate limited

Back off for the number of seconds in the \`Retry-After\` header. Every response also carries \`X-RateLimit-Remaining\`, so a well-behaved client can throttle itself before hitting the wall.
`,
  },
];

export const DOC_SLUGS = DOCS.map((d) => d.slug);

export function getDoc(slug: string): DocPage | undefined {
  return DOCS.find((d) => d.slug === slug);
}

export function docsBySection(): Array<{ section: DocSection; pages: DocPage[] }> {
  return DOC_SECTIONS.map((section) => ({
    section,
    pages: DOCS.filter((d) => d.section === section),
  })).filter((group) => group.pages.length > 0);
}

/** Ordered neighbours for prev/next navigation at the foot of each page. */
export function docNeighbours(slug: string): { prev?: DocPage; next?: DocPage } {
  const index = DOCS.findIndex((d) => d.slug === slug);
  if (index === -1) return {};
  return { prev: DOCS[index - 1], next: DOCS[index + 1] };
}
