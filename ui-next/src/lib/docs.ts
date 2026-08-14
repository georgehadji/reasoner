/**
 * Documentation content registry.
 *
 * Docs are plain data rather than MDX so that every page is a static server
 * component: the full prose ships in the first HTML response, which is what
 * makes the docs readable by search crawlers and by AI answer engines that do
 * not execute JavaScript.
 */

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

export type DocSection = 'Getting started' | 'Reasoning' | 'Billing' | 'Developers' | 'Operations';

export const DOC_SECTIONS: DocSection[] = [
  'Getting started',
  'Reasoning',
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
      'How the 48 presets map to reasoning methods, what Budget and Premium change, and how model routing and fallbacks work.',
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

There are 48 presets in total. The picker lists them cheapest-first and defaults to the cheapest option, so cost is opt-in rather than opt-out.

Leaving the preset on **Auto** lets HyperGate pick both the method and the tier from the problem itself.

## Models

Reasoner routes across 28 directly registered models and 350+ more through OpenRouter, spanning Anthropic, OpenAI, Google, DeepSeek, Mistral, xAI, Qwen, Moonshot, Zhipu, MiniMax, Perplexity, and locally hosted Ollama models.

Routing is by **role**, not by preference. Each phase requests a role — generator, scorer, synthesiser, searcher — and the router resolves it against the preset's routing table.

## Fallbacks

When a provider fails, times out, or trips its circuit breaker, the router falls back to a **cross-lab equivalent**, never to the preset's primary model. A blind fallback to the primary would quietly collapse the diversity guarantee at exactly the moment things are going wrong, which is when you can least afford it.

Circuit breakers are per-provider. A provider that keeps failing is skipped entirely until it recovers, rather than being retried on every phase.

## Estimating cost before you run

\`POST /api/estimate\` returns a projected token and cost range for a given problem and preset. The composer calls it as you type, which is where the cost figure next to the run button comes from.
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
