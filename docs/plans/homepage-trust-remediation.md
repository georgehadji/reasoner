# Home Page Trust & Credibility Remediation Plan

**Status:** Draft · **Created:** 2026-08-17 · **Branch target:** `review-rebase` → feature branch per phase
**Scope:** public marketing surface (`/`, `/security`, `/about`, `/privacy`, footer, header) + the
code-derived data that feeds it. No pipeline/domain logic changes.

---

## 0. Governing principle

> Every number, badge, and guarantee on a public page must be either (a) derived from code at build
> time, or (b) traceable to a document in this repo. Anything else gets deleted or moved under an
> explicitly-labelled roadmap heading.

The current site fails this in eleven places. A single busted claim discovered by a procurement
reviewer costs more than every conversion optimisation on this page combined. Truth pass ships
first; everything else is layered on top of it.

### Architecture rules this plan respects

| Rule | Consequence for this plan |
|---|---|
| Capability counts live in Python (`infrastructure/llm/registry.py`, `domain/preset_registry.py`, `phases/`) | UI never hardcodes them. Counts are generated into a TS module, not fetched at runtime and not retyped by hand. |
| `scripts/update_mindmap_meta.py` already derives counts from live code and runs on `post-commit` | Extend that script rather than adding a second generator + second hook. |
| `ui-next/src/lib/site.ts` is declared "single source of truth for site identity" | Generated capability numbers are imported *by* `site.ts`; components read from `site.ts`, never from each other. |
| `ui-next/src/lib/docs.ts` — content as plain data so pages stay static server components | New marketing/trust content follows the same data-registry pattern. No MDX, no client components for text. |
| Tailwind v4, CSS-native tokens (`--space-*`, `--text-*`, `--accent`) | `/security` is currently raw Tailwind (`text-4xl`, `green-500`, `rounded-2xl`) and must be migrated onto tokens as part of its rewrite. |
| Each `lib/config.ts` `API.*` constant needs a matching `src/app/api/*/route.ts` proxy | Only relevant if a phase adds a backend-backed endpoint. Phases 1–5 deliberately avoid that. |
| `lib/site.ts` `NOINDEX_PATHS` + `sitemap.ts` must not drift | Every new public route is registered in both, same commit. |

---

## Phase 0 — Truth pass (BLOCKING, ship alone)

No new features. Text and two dead handlers only. Merge before any other phase starts.

### 0.1 License reconciliation

Project is **commercial**. Repo currently asserts MIT in four places.

| File | Current | Action |
|---|---|---|
| `LICENSE` | MIT, © Georgios-Chrysovalantis Chatzivantsidis | Replace per decision below |
| `README.md:11` | `![License: MIT]` shields badge | Replace badge |
| `README.md:30` | `**License:** MIT` | Replace |
| `README.md:533-535` | `## License` → `[MIT](LICENSE)` | Replace |
| `sdk/typescript/package.json:5` | `"license": "MIT"` | See open-core note |
| `pyproject.toml` | no license field | Add explicit field so packaging can't infer |
| `ui-next/.../LandingPage.tsx:146-148` | "Open Source. MIT licensed. Audit the code…" | Delete or rewrite per decision |

**Decision required (D-1).** Three viable shapes:

1. **Fully proprietary.** `LICENSE` → commercial EULA. Drop "open source", "audit the code",
   "fork it". Self-hosting becomes a paid-tier feature, described as "deploy in your own VPC",
   not as an open-source right.
2. **Source-available (BSL 1.1 / Functional Source License).** Code readable and self-hostable,
   competing commercial use prohibited, converts to Apache-2.0 after N years. Preserves the
   "audit the code / self-host" trust argument — which is the single strongest privacy signal the
   site has — while blocking competitors.
3. **Open-core.** Engine under (1) or (2); `sdk/typescript` stays MIT/Apache-2.0.

**Recommendation: 2 + 3.** FSL or BSL 1.1 on the engine, MIT on the SDK. Client SDKs under a
restrictive licence do not get installed; and the self-host/auditability claim is worth more on the
security page than the theoretical risk it guards against.

**Verification tasks before choosing:**
- Confirm `github.com/georgehadji/reasoner` (then misspelled `Reaseoner`, renamed 2026-08-18 —
  see D-6) was never public under MIT (it currently 404s, so a clean slate is likely). Any prior
  public commit stays MIT-licensed for that revision, permanently.
- Confirm `.github/workflows/release-sdk.yml` never published `@reasoner/sdk@0.2.0` to npm under MIT.

### 0.2 False-claim purge

| # | Claim | Location | Replacement |
|---|---|---|---|
| 1 | "Open Source. MIT licensed. Audit the code, fork it" | `LandingPage.tsx:146` | Per D-1. If (2)/(3): "Source-available. Read the code, run it in your own infrastructure." |
| 2 | "No hallucinations pass through." | `LandingPage.tsx:54` | "Claims that survive cross-model verification are labelled VERIFIED; the rest are labelled HYPOTHESIS or UNKNOWN — never silently presented as fact." |
| 3 | "100% verified output" | `LandingPage.tsx:85` | "Every claim epistemically labelled" |
| 4 | "17 reasoning methods / 90+ AI models / 6 model labs" | `LandingPage.tsx:82-86` | Generated values (Phase 1). Interim: 19 / 350+ / 12, matching `lib/site.ts:shortDescription`, which is already correct — the drift is between two files in the same repo. |
| 5 | "GDPR & HIPAA: Full compliance…" | `security/page.tsx:37` | Split. GDPR: state the concrete measures (data location, retention, deletion, DPA on request, sub-processor list). HIPAA: delete unless a BAA is actually offered. |
| 6 | "request our latest SOC 2 report" | `security/page.tsx:107` | Delete. Contradicts line 73 on the same page ("designed for SOC 2 Type II"). |
| 7 | "Certified SOC 2 Type…" | `SecurityModal.tsx:70` | Delete. Hardest claim on the site, rendered in the footer of **every** page. |
| 8 | "Full GDPR and HIPAA…" | `SecurityModal.tsx:85` | Same treatment as #5. |
| 9 | "SAML 2.0 and OIDC (Okta, Azure AD, Google)" | `security/page.tsx:89` | No SAML/OIDC exists in `src/`. Move under "Roadmap" or delete. |
| 10 | "built to the highest enterprise standards" | `security/page.tsx:17` | Replace with specifics. Superlatives without evidence read as filler. |
| 11 | "Ready for Enterprise?" + "Enterprise-Grade Reasoning" | `security/page.tsx:105`, `LandingPage.tsx:385` | Keep only if SSO/SLA/DPA exist. Otherwise reposition — an enterprise buyer who finds no SSO after the headline discounts everything else on the page. |

### 0.3 Dead controls

`security/page.tsx:111` "Contact Security" and `:114` "View Docs" are `<button>` with no handler.
Convert to `<Link>` → `/contact` and `/docs`. Dead controls on a security page are the exact signal
the page exists to disprove.

### 0.4 Claims that are TRUE and currently unused

Underclaimed assets, to be surfaced in Phases 2–3:

- AES-256-GCM at rest, encryption v2 with key rotation — `ENCRYPTION.md`, `migrations/008_encryption_indexes.sql`
- Real audit logging — `src/reasoner/api/saas_router.py`
- Internal security audit, dated — `docs/audits/2026-08-16-security-audit.md`
- 225 test files, CI with coverage gates — `.github/workflows/test.yml`, `self-healing-ci.yml`
- Automated secret scanning — `scripts/scan-secrets.py`, `.github/workflows/security.yml`
- Self-hostable full stack — `docker-compose.yml`, own Postgres + Valkey
- Typed SDK + OpenAPI digest + MCP server + `llms.txt` — `sdk/`, `docs/MCP.md`
- Architectural discipline — import-linter contracts, hexagonal boundaries

### Acceptance — Phase 0
- [ ] `rg -i "SOC 2|HIPAA|MIT|100% verified|no hallucinations" ui-next/src` returns only intended hits
- [ ] Every remaining compliance noun on a public page maps to a repo document or a signed contract
- [ ] No `<button>` without a handler in `ui-next/src/app/{security,about,pricing,contact}`
- [ ] New test `ui-next/src/lib/claims.test.ts`: forbidden-phrase regex over `src/app/**` and
      `src/components/**`, fails the build on reintroduction. Cheapest possible ratchet.

---

## Phase 1 — Capability numbers derived from code

**Problem:** three sources disagree — `LandingPage.tsx` (17/90+/6), `lib/site.ts` (19/350+),
`CLAUDE.md` (19 methods, 28 direct, 350+ via OpenRouter, 48 presets, 12 adapters).

**Approach:** extend the existing generator; do not add a second one.

### 1.1 Extend `scripts/update_mindmap_meta.py`

It already computes `_count_models()`, `_count_presets()`, `_count_methods()`, `_count_py_files()`
from live imports and runs on `post-commit`. Add one emitter:

```
ui-next/src/lib/capabilities.generated.ts   (new, committed, header: DO NOT EDIT)
```

```ts
export const CAPABILITIES = {
  methods: 19,
  presets: 48,
  directModels: 28,
  routableModels: 350,
  providerAdapters: 12,
  testFiles: 225,
  generatedAt: '2026-08-17',
} as const;
```

Also emit the provider list needed by Phase 2.3:

```ts
export const PROVIDERS = ['Anthropic', 'OpenAI', 'Google', /* … from registry */] as const;
```

### 1.2 Consume

- `lib/site.ts` — build `shortDescription` from `CAPABILITIES` instead of a literal.
- `LandingPage.tsx` — `CAPABILITIES` array built from the generated constants.
- Anywhere else a count appears (`/about`, `/docs`, `/pricing`) — same import.

### 1.3 Drift guard

`tests/test_site_capabilities_sync.py` — regenerate into a temp buffer, compare against the
committed file, fail if different. Same shape as the existing preset-validation tests. This is what
makes the generation trustworthy instead of decorative.

### Acceptance — Phase 1
- [ ] `rg -n "\b(17|90\+|6 model)" ui-next/src` → no hits
- [ ] No literal capability integer outside `capabilities.generated.ts`
- [ ] Sync test green; deliberately editing a preset makes it red

---

## Phase 2 — Trust surface

### 2.1 `/security` rewrite

Rebuild on design tokens (current page predates the token system: raw `text-4xl`, `green-500`,
`rounded-2xl`). Structure:

1. **What we do today** — encryption at rest/in transit with the actual algorithm; audit logging;
   secret scanning in CI; dependency scanning; token-bucket rate limiting; CSRF; prompt-injection
   sanitisation; circuit breakers. Each line links to its evidence (`ENCRYPTION.md`,
   `docs/audits/…`, workflow file, or `/docs` page).
2. **Where your data goes** — model providers named, per request path. This is the question every
   serious buyer actually asks and no competitor answers plainly.
3. **What we do not do** — no training on customer data; no third-party analytics on the app
   surface (verify before claiming); retention window stated in days, with the deletion mechanism.
4. **Self-hosting** — the escape hatch. For a privacy-blocked buyer this closes the deal alone.
5. **Roadmap**, explicitly labelled — SOC 2, SSO/SAML, BAA. Honest "not yet" outperforms a claim
   that fails diligence.
6. **Report a vulnerability** — link to `security.txt` and a real contact.

### 2.2 `public/.well-known/security.txt` (RFC 9116)

```
Contact: mailto:security@<domain>
Expires: <ISO 8601, ≤1 year out>
Preferred-Languages: en
Canonical: https://<domain>/.well-known/security.txt
Policy: https://<domain>/security
```

Cheapest credibility artefact in existence. Note `Expires` is mandatory — add a calendar reminder
or a CI check that fails within 30 days of expiry.

### 2.3 `/subprocessors` (new route)

GDPR-serious buyers look for this before they look at the word "GDPR". Generate the table from
`PROVIDERS` (Phase 1.1) so it cannot go stale when routing changes: provider, purpose, data
categories, region, DPA link. Register in `sitemap.ts`; link from `/privacy` and `/security`.

### 2.4 `/privacy` hardening

Add concrete retention periods, deletion path, data-export path, DPA-on-request, controller identity
and jurisdiction. Cross-link `/subprocessors`.

### 2.5 Legal identity

`/about` (69 lines) contains no company, entity, jurisdiction, or team. Add: legal entity name,
registered address, contact, and a named human. Anonymous vendor = unsafe vendor; in the EU an
imprint is also expected. Mirror the entity line in `SiteFooter.tsx`.

### 2.6 Footer expansion

`SiteFooter.tsx` `LINKS`: add **Status**, **Changelog**, **Sub-processors**, **Security.txt**, and
fix `Docs → /help` (should be `/docs`; the header already points at `/docs`, so the two disagree).

### Acceptance — Phase 2
- [ ] `/security` uses tokens only; passes the same a11y bar as `LandingPage`
- [ ] Every claim on `/security` links to evidence or is under "Roadmap"
- [ ] `security.txt` resolves with valid, unexpired `Expires`
- [ ] `/subprocessors` generated, in sitemap, linked from privacy + security
- [ ] Legal entity visible on `/about` and in the footer

---

## Phase 3 — Product proof on the home page

Current hero is text-only. Highest-converting pattern for developer tools is showing the product;
this product's differentiator (streaming multi-phase reasoning with epistemic labels) is inherently
visual and is currently invisible until after signup.

### 3.1 Hero visual

Static, optimised `next/image` of a real run showing phase progression and VERIFIED / HYPOTHESIS /
UNKNOWN badges. Must have a light and a dark asset — the page is theme-aware. Ship this before the
interactive demo; it captures most of the value at a fraction of the work.

### 3.2 Canned demo (`components/landing/DemoReplay.tsx`)

**Not** a live backend call: no auth, no cost, no rate limit, no outage dependency, no abuse
surface.

- Record one real run's SSE event stream → `ui-next/src/lib/demo-run.json`.
- Replay client-side on a timer, typed against `sdk/contract/events.json` (the contract module
  already exists and is already tested against the backend by `tests/test_sdk_contract.py`).
- Reuse existing phase components in `components/phases/` — same rendering path as the real app, so
  the demo cannot drift into showing a UI that no longer exists.
- Respect `prefers-reduced-motion`: render the final state immediately, no replay.
- Gate the whole section behind the existing `RevealSection`, and keep the JSON out of the initial
  bundle via dynamic import.

### 3.3 Developer section

New landing section between "How it works" and "Security":
`curl` example, `npm i @reasoner/sdk` snippet, links to `/docs`, the OpenAPI digest, `docs/MCP.md`,
`llms.txt`. This audience grades on API surface; it is fully built and entirely unadvertised.

### 3.4 Pricing + FAQ on the home page

- Pricing teaser (free tier, "20 queries/month", link to `/pricing`). Transparent pricing is itself
  a trust signal, and the page currently never mentions cost.
- FAQ block sourced from the existing `lib/faq.ts` registry — five objections: training on data,
  retention, which providers see my prompt, what happens at capacity, EU data residency.

### 3.5 Provider strip

Model-lab wordmarks (Anthropic, OpenAI, Google, Mistral, DeepSeek, xAI…) under the hero, framed as
**"Routes across"**, never "Trusted by". Borrowed credibility that is factually accurate; check each
vendor's trademark-usage policy before shipping the marks.

### Acceptance — Phase 3
- [ ] Hero shows the product in both themes; LCP not regressed (measure before/after)
- [ ] Demo replays with JS on, degrades to a static final frame with JS off / reduced motion
- [ ] Demo types check against `sdk/contract/events.json`
- [ ] Lighthouse a11y ≥ existing score; no CLS from the demo

---

## Phase 4 — Operational credibility

### 4.1 Status page
External provider (BetterStack / UptimeRobot free tier) monitoring `/api/health`, linked from
footer. **Do not self-host it** — a status page served by the infrastructure it reports on is
worthless during the only incident that matters.

### 4.2 Changelog
`/changelog` as a data registry (`lib/changelog.ts`), same static-server-component pattern as
`docs.ts`. A dated, moving changelog is the single clearest "this is maintained" signal. Backfill
from git history for the last few releases.

### 4.3 Public repo decision (follows D-1)
- Option 2/3 → publish the source-available repo, link it, keep the "read the code" claim.
- Option 1 → no public repo; replace the auditability claim with a published, redacted version of
  `docs/audits/2026-08-16-security-audit.md`, which serves the same purpose and is already written.

---

## Phase 5 — Social proof (last)

Zero social proof today, and a weak testimonial converts worse than none. Build the slots, leave
them unrendered until real content exists:

- `components/landing/Testimonial.tsx` — renders `null` when no entry is present. No placeholder
  faces, no invented quotes, no "trusted by thousands".
- Prefer specificity when filling: named user + role + concrete outcome beats a logo wall.
- Interim substitutes that are honest today: usage numbers once real, the published audit, the
  changelog cadence, the public test count.

---

## Sequencing

| Phase | Depends on | Rough size | Ship separately? |
|---|---|---|---|
| 0 Truth pass | D-1 decision | S — text + 2 handlers | **Yes, first, alone** |
| 1 Generated counts | 0 | S | Yes |
| 2 Trust surface | 0, 1 (providers) | M | Yes |
| 3 Product proof | 0, 1 | M–L (demo is the bulk) | 3.1 first, 3.2 after |
| 4 Ops credibility | 0, D-1 | S | Yes |
| 5 Social proof | real users | S scaffold | Deferred |

Phase 0 blocks everything: layering features over false claims multiplies the eventual correction.

## Open decisions

| ID | Decision | Owner | Blocks |
|---|---|---|---|
| D-1 | Licence shape — proprietary / source-available / open-core | You | 0.1, 4.3, hero copy |
| D-2 | Pursue SOC 2 Type II, or state "not certified" plainly | You | 2.1 |
| D-3 | Legal entity + registered address to publish | You | 2.5 |
| D-4 | Actual retention period and deletion SLA | You | 2.1, 2.4 |
| D-5 | Is HIPAA in scope at all (BAA offered)? If not, delete every mention | You | 0.2 |
| D-6 | ~~Rename repo `Reaseoner` → `reasoner` before any public link~~ — **done 2026-08-18.** Renamed on GitHub (still private, so nothing public pointed at the old slug); local remote and the three hardcoded references updated in `d1a7653`. GitHub redirects the old path, and a dead command-allowlist entry in `.claude/settings.local.json` was removed. The remaining mentions of the old slug (§0.1, above) are deliberate — quoted as historical fact, dated to the rename | — | 4.3 |

## Explicitly out of scope

Trust-center portal (a truthful `/security` covers it pre-SOC 2) · visitor personalisation (no
traffic to segment) · design-system rework (the landing tokens are good) · live public demo backend
(recorded replay covers it at zero cost/risk) · pipeline, domain, or infrastructure changes.
