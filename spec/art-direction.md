# Art direction — "The product performs"

Adopted 2026-11-13. Replaces Overprint (two riso inks on newsprint), which is retired.
Dealt by the taste-skill draw (`.taste-skill/direction.json`, seed 2138486423), direction
`product-performs`, chosen over `sentence-as-layout` and `quiet-instrument` because Reasoner's
proof is its own output: a run record anyone can handle on the page.

## 1. The idea

> On this page, **one real Reasoner run** becomes **the working fragments the visitor
> handles**: its claim labels switch on and off, its critic's score sheet answers the
> pointer, its routing refuses labs when Western-only is on.

Competitor test: another AI product cannot put a cross-lab critique table and per-claim
verified / hypothesis / unknown labels from its own captured run on its page. Every
fragment's content comes from `ui-next/src/lib/demo-record.ts` (captured 2026-08-17),
`lib/sectors.ts`, or `lib/capabilities.generated.ts`. Nothing is typed by hand except copy.

**The live thing:** the hero's "Answer only / With the record" switch.

## 2. Composition

- No navigation bar on the home page: logo top-left, one text link ("Open the app") top-right.
- Hero: two halves meeting at 50%, the right one tone lighter. Left: the headline anchored
  bottom-left, one sentence, one button. Right: the live fragment at interface size.
- Sections never repeat a neighbour's layout. Each is a blueprint from the sheet:
  critique (input half / output half), labs (large names on tiles, heading tile in the
  accent), sectors (tabs over banded review sheet), pilot (pinned fragment changing state),
  capabilities (giant command list), own claims (narrow labelled list), start (create dialog
  already open on an accent field), footer (one quiet line).
- Fragments are cropped interface, marked `data-ui`, never in a browser or device frame.
  Inside `data-ui` the product's conventions apply: 1px control borders, small radii,
  uppercase epistemic marks, a shadow only on the open dialog.

## 3. Colour — charcoal and sage

The dealt "black and crimson" palette was redrawn: near-black with one crimson accent is
the banlist's "near-black background with a single acid-green or vermilion accent".

| Role | Token | Value |
|---|---|---|
| Ground | `--site-bg` | `#1C1C1C` |
| Lighter half, tiles, panels | `--site-surface` / `--site-surface-2` | `#262626` / `#303030` |
| Ink | `--site-ink` | `#F1F1EF` |
| Secondary ink | `--site-muted` | `#A3A49F` |
| Accent: the one button, active controls, two fields | `--site-accent` | `#8FA68E` |
| Light field (critique output half) | `--site-field` | `#C8C5BA` |
| Verified / hypothesis / unknown | `--ok` / `--warn` / `--unknown` | `#6CC4C0` / `#E0A458` / `#C9C9C3` |

The site is charcoal in both colour schemes. Epistemic labels keep their carrier (solid /
dashed / dotted rule) so they survive monochrome print. Every text pair clears AA; the lowest is the accent on `--site-surface-2` at 5.04:1
(figures in tokens.css).

## 4. Type

- Display: **League Spartan 700**, tracking -0.04em, sentence case, two lines at most.
- Text: **Figtree 400 / 600**, leading 1.5. Body copy 17–19px, never below 13px.
- Mono: **Inconsolata**, code and citations inside fragments only.
- Five steps: `--site-small`, `--site-body`, `--site-lead`, `--site-head`, `--site-display`.

Fonts swapped app-wide in `ui-next/src/app/fonts.ts` (the app keeps its own colours until its
run). Budget: two text families plus one mono, three weights, self-hosted by next/font.

## 5. Motion

One loud moment: each headline line rises from behind its baseline (900ms, second line
110ms later), then the sentence and button fade up. Around it: one-time section entrances
(`Reveal.tsx`, armed only by script and only when motion is allowed), feedback on every
control, the pinned pilot fragment changing state. All of it collapses under
`prefers-reduced-motion`.

## 6. Where it lives

- Tokens: `ui-next/src/styles/tokens.css`, block "SITE WORLD", scoped to `.site`, which
  remaps the app's role names so shared components follow.
- Layer: `ui-next/src/app/globals.css`, block "Site world" (Overprint ornaments off, masked
  headline, reveals, `.site-button`, `.site-link`).
- Components: `ui-next/src/components/site/`.

## 7. Status

- Done: home page (`components/landing/LandingPage.tsx`). Inspector: 0 FAIL at 1440 / 768 /
  390 (`.taste-skill/after/`).
- Defended warnings: no photographs or footage (software with no photography; its pictures
  are its interface fragments); the critique heading sits at the foot of its section by
  design; the critic's input
  excerpts are quoted material in secondary ink.
- Phone hero (2026-11-14): headline, sentence and button first, the live fragment after, so the
  h1 is on the first screen. The inspector walks at most 11 screens after the fold; at 390px the
  home page is about 13.6 screens, so `#start` is never scrolled into view there and reports a
  blank gap. Visitors do reach it; this is a measurement limit, not an empty section.
- /security rebuilt (2026-11-14): controls sheet with a status filter, request path, Compose
  file, security.txt as served. Inspector: 0 FAIL at 1440 / 768 / 390 (`.taste-skill/pages/security/`).
  The site header now switches to the drawer below `lg`: at 768px the six links and the actions
  ran past the right edge.
- /privacy rebuilt (2026-11-14): the store registry (`lib/user-data-stores.ts`, mirrored from
  `api/user_data.py`) with a live "erase my data / delete my account" preview, export and
  erasure receipt fragments. Removed a "last updated" that printed today's date and an
  AES-256-GCM claim the body contradicted. Inspector: 0 FAIL at 1440 / 768 / 390.
- /pricing rebuilt (2026-11-14): live "how far a month goes" meter (`lib/credits.ts`, mirrored
  from `domain/credits.py`), plan sheet with the Stripe / PayPal checkout kept, ledger reasons,
  `GET /api/credits/pricing` as served. Prices stay [INPUT REQUIRED]. Inspector: 0 FAIL.
- /contact rebuilt (2026-11-14): form beside the email it becomes (format from
  `routes/contact.py`, updates as you type), FAQ shortcuts, security.txt, the route's 200 / 503
  answers. Dropped an unbacked "reply within 24 hours". Inspector: 0 FAIL.
- /for/[sector] rebuilt (2026-11-14): sector name as the headline, the reviewer's gating
  question as the lead, a printable review sheet as the hero fragment (status per question,
  `PrintButton`), every answer as `StatusBands`, the reachable providers, the captured run
  record on the field, and the pilot with the sector's methods (`SectorMethod` hints from
  `METHOD_HINTS_DATA`). Defence is marked Western-only. Inspector: 0 FAIL on all six sectors.
- /how-it-works rebuilt (2026-11-14): one captured run walked phase by phase, each phase's
  real output as a fragment (sources with cited/read, the four positions, critic scores with
  kept/pruned and bias flags, stress tests, the synthesis toggle, the API call and ledger).
  `RunIndex` is now the hero (timing chart + contents); the synthesis reads inside a scrolling
  reader capped by `--site-reader-h`. Dropped the "Terms" block: /security owns those claims.
  The rail's "N VERIFIED" counted every label kind; it now counts each kind. Inspector: 0 FAIL.
- /capabilities rebuilt (2026-11-14): "What holds each claim." with a fragment naming what
  holds each of the eight mechanisms (rule in code, test, or brief to a model), then the eight
  sections with their audited copy unchanged in substance, fragments for the label rule, image
  families, prose tells, the research loop and the methods. `Section`/`Body` stay local so
  `tests/test_site_capabilities_sync.py` still parses the gated #sycophancy section.
  `.site-link` pins dark-ground ink, so links on the light field add `text-current`.
  Inspector: 0 FAIL at 1440 and 768; 1 FAIL at 390, blank-gap past the 11-screen walk
  (page is 14.4 screens; unscrolled `Reveal` sections stay armed), the same artifact as home.
- /developers rebuilt (2026-11-14): "An answer your code can act on." beside the sync call and
  its response, then the seven sections with fragments for the MCP config and six tools, the
  CLI, the discovery endpoints and the statuses. The section chrome moved out of
  /capabilities into `site/ArgumentSection.tsx`, shared by both; `landing/prose.tsx` had no
  importers left and was deleted. A hero cell holding `<pre>` needs `min-w-0`, or the code's
  longest line widens the page at 390. Inspector: 0 FAIL.
- /about rebuilt (2026-11-14): "Nothing asks to be believed." beside the page's own claims,
  each labelled VERIFIED or HYPOTHESIS, then six `ArgumentSection`s with fragments for the
  regenerated counts, the three routing rules, the four commitments with their cost, and the
  sycophancy controls listed from `SYCOPHANCY_CONTROLS`. Claims corrected: the unfinished
  section said no sycophancy mitigation was built (7 of 10 are); the privacy commitment now
  matches the corrected security wording (no training on user data, providers have their own
  terms); "20 questions a month" became the 500 free credits from `TIER_CREDITS`.
  Inspector: 0 FAIL.
- /faq rebuilt (2026-11-14): "Asked first, answered here." beside an index of every question,
  then the answers printed in full (no accordion) in four `ArgumentSection`s grouped by the new
  `topic` field in `lib/faq.ts`, with fragments for the credit table, a streamed agent run and
  what the erase endpoint removes. Claims corrected: the API answer named `POST /api/run`,
  which takes CSRF, not a bearer key (now `/api/agent/run` and `/run/sync`); Neuro Memory
  "can be cleared at any time" became "erased with your data through the API". Inspector:
  0 FAIL.
- /cookies rebuilt (2026-11-14): "One cookie, and why." beside the CSRF cookie set out the way
  a browser's storage panel shows it, then how the token travels, every browser-storage key,
  and what is absent. Names and lifetimes import from `security-constants.ts`, `config.ts`
  and `pilot-draft.ts`. Claims corrected: "Last updated" printed today's date on every visit
  (now an `[INPUT REQUIRED]` effective date); sign-in was described as a cookie, but supabase-js
  keeps the session in localStorage; theme and sidebar were "cookies", both are localStorage.
  Inspector: 0 FAIL.
- /terms rebuilt (2026-11-14): "Terms of service." beside a numbered summary that says it is
  one, then the six sections with fragments for the source licence (from LICENSE), the
  epistemic labels and the prohibited uses. The legal wording is kept; nothing new was
  drafted. Corrected: "Last updated" printed today's date; "99.9% uptime" had no measurement
  (/status publishes no history); a reverse-engineering ban contradicted the published BSL
  source and is replaced by the licence's one restriction (no hosted resale); the metadata
  promised billing and liability sections that do not exist. Jurisdiction and effective date
  are `[INPUT REQUIRED]`. Inspector: 0 FAIL.
- /subprocessors rebuilt (2026-11-14): "Who else sees your request." beside one run's path out
  of our servers, then every model maker a run can reach, the direct fallbacks with their
  privacy policies, and the services around the model call (search, sign-in, payments, email,
  error reports). Corrected: the page said its list "cannot go stale" yet named only the eight
  direct fallback adapters; every call goes through OpenRouter first, which reaches 30 makers.
  The makers now come from `MODEL_VENDORS`, generated into `capabilities.generated.ts` by
  `scripts/update_mindmap_meta.py`. Three pages said every provider was listed "with its
  privacy policy"; only the direct fallbacks have one linked, so that phrase is gone. Host
  pinning and hosting region are `[INPUT REQUIRED]`. Inspector: 0 FAIL.
- /changelog rebuilt (2026-11-14): "What shipped, and when." beside the latest entry, then one
  section per month generated from `CHANGELOG`, in fragments of at most five entries so none
  runs past a phone screen and a half. Every entry now names its commit on main. Corrected: the
  list had stopped at 2026-08-16 while nine user-facing changes landed after it; those are
  added, each traced to a commit. Work on unmerged branches is left out. Inspector: 0 FAIL.
- /status rebuilt (2026-11-14): "Checked as you load it." beside the live `GET /api/health`
  panel, which lists the six checks in every state (checking, answered, no answer) so it keeps
  its height. Sections say what each check really tests (`lib/status-checks.ts`, mirrored from
  `health_service.py`), how the one-word verdict is chosen, the public response shape, and
  what the page does not publish. Corrected: the `/api/health` proxy asked the backend root,
  which has no `status` field, so the page read "Service disruption" while the API was up; it
  now asks `/api/health` (route test added). Also said plainly: the cache check always reports
  OK and the billing check only confirms a Stripe key is set. Inspector: 0 FAIL.
- Site chrome simplified (2026-11-14, Maeda's laws of simplicity): the header lost its theme
  toggle (a `.site` page is charcoal in both schemes; `/settings` still passes `themeToggle`),
  its "Secure" badge (/security makes that case), and its glass and shadow when scrolled (now a
  flat ground and a hairline). Its one action reads "Open the app" signed in or out, and every
  header action is a `<Link>`, so it prefetches and opens in a new tab. The footer's 14 links
  are grouped as Product, Build, Trust and Company, and /cookies is now among them.
- Rolled out (2026-11-13, tokens and chrome only): `.site` on every marketing page root,
  `SiteFooter` is now the quiet line, inverted bands flip to the concrete field, uppercase
  micro-labels and prose mono removed, `Reveal` mounted in `SiteHeader`. Their layouts are
  still the old ones and each fails the inspector 3–9 times (no pictures, thin rules,
  headlines over two lines, off-centre columns, too little motion).
- Next: rebuild each marketing page's composition from blueprints (/how-it-works,
  /capabilities, /developers, /security, /privacy, /pricing, /contact, /for/[sector], /about),
  replacing `SiteHeader` / `SiteFooter` there. Then the app screens as their own run.
- Sample content to confirm: the pilot example problems in `PilotPinned.tsx` and
  `PilotDialog.tsx` are illustrations, not client work.
