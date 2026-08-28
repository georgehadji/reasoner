<!--
Produced by the reasoner-redesign-direction workflow (run wf_0cc49fe1-37b, 2026-08-28):
4 census agents -> 1 diagnosis -> 4 mutually-blind directions -> 12 adversarial judges
-> 1 synthesis. The four rejected directions and all 12 verdicts are in that run's
journal.jsonl.

Diagnosis recorded genericness 8/10 for the incumbent design.

Spot-verified against the tree before adoption: the three emoji widgets, --space-40
undeclared while used at CapabilitiesPage.tsx:130 and DevelopersPage.tsx:151, the four
hardcoded hexes in app/global-error.tsx, and the var(--accent) call-site magnitude.
Counts below are the workflow's; treat any single number as INFERENCE until the step
that touches it re-counts.
-->

# Art Direction — Reasoner

**Status:** recommendation, ready to build. Every number below was recomputed from the tree or from the OKLCH values given; the calibration check is that my WCAG implementation reproduces all ten of `globals.css`'s existing annotations to within 0.05 (`#756F65` on `#FAF9F5` → 4.73 against an annotated 4.7).

---

## 0. The finding that reorders all four directions

Before the recommendation, one measurement that none of the four directions made and that invalidates three of the four signatures.

I parsed `ui-next/src/lib/demo-run.json` (37 events) and counted epistemic labels per event:

| Event | Phase | Words | Labels |
|---|---|---|---|
| 7 | **Phase 2 — Perspectives** (4 candidates) | 975 | **16** |
| 9 | Phase 3 — Critique | 104 | 0 |
| 11 | Phase 4 — Stress | 70 | 0 |
| 13–33 | **Phase 5 — Synthesis** (21 `text_chunk`s) | ~440 | **1** |

**The labels are dense in the perspectives and effectively absent from the answer.** One label per 61 words in Phase 2; one label in the entire synthesis.

Grade points its confidence gutter at the synthesis. Apparatus points its 9rem epistemic gutter at the synthesis. Off-Register points its split rule at every claim-bearing block. All three render a blank margin beside the thing a paying user actually reads. This is not a fixable detail — it is the load-bearing assumption of three signatures, and it is false.

What *is* dense and structured, verified from the same file:

- **Phase 2** — 4 candidates, each `{perspective, content, key_insights, model_used}`, across 3 distinct model IDs (`nousresearch/hermes-4-70b`, `mistralai/mistral-small-3.2-24b-instruct`, `grok-4.3`), carrying those 16 labels.
- **Phase 3** — 4 scores, each `{perspective, logical_consistency, evidence_support, failure_resilience, feasibility, total, bias_flags, steel_man, is_top}`, judged by **one** model. A 4×4 matrix with post-penalty totals, the judge's own bias flagged, and the strongest form of each *rejected* position preserved in `steel_man`.
- **Phase 4** — 2 scenarios, each `{scenario, survival_rate, failure_mode, recovery_path}`. `survival_rate` is a real number (0.88).

There is **no per-claim agreement count and no per-claim variance anywhere**. Off-Register's `--split` and Apparatus's `9/9 · 4/9 · 0/9` gutter figures are both unsourceable; inventing them violates the same discipline that makes `Testimonial.tsx:15-19` return `null` rather than fabricate a quote.

**Consequence: the signature must be anchored to the critique and the perspectives, not to the synthesis.** That is where the product's central claim has data behind it, and it is the one shape no chatbot's backend can emit — a chatbot has one answer, so it has no matrix and no rejected positions to keep.

### A second finding: the "contrast discipline" is disciplined against one ground out of nine

The census calls the per-token contrast annotations the repo's best work. They are a good *habit* applied to one denominator. Every annotation in `globals.css` measures against `--bg`. Measured against the eight other grounds the same ink actually renders on, the incumbent ships **seven live sub-AA pairs**:

```
--text-subtle #756F65 on --surface-2  #F1EFE7   4.32  FAIL
--text-subtle #756F65 on --surface-3  #E6E3D8   3.87  FAIL
--text-muted  #6E6960 on --surface-3  #E6E3D8   4.24  FAIL
--text-muted  #6E6960 on --sidebar-hover  #E8E5DA   4.32  FAIL
--text-muted  #6E6960 on --sidebar-active #DFDBCC   3.93  FAIL
dark --text-subtle #857F74 on --surface   #1C1A18   4.37  FAIL
dark --text-subtle #857F74 on --surface-3 #302D29   3.45  FAIL
```

And `--border-strong`, whose comment cites WCAG 1.4.11's 3:1 by name, measures **1.80:1 in light** (`rgb(19 18 17 / .26)` on `#FFFFFF`) and **2.15:1 in dark**. It fails the criterion it was written to satisfy.

So "preserve the contrast discipline" is not preservation. It is **completion**, and it is the single cheapest correctness win in this exercise.

---

## 1. RECOMMENDATION — **Apparatus**, with two structural amendments

**Build Apparatus.** Not because it has the best average (all four sit at 5.7–6.0), but because it is the only direction whose *thesis* survives the data check while its *fatals* are all resolvable inside the frontend.

### Argued against the scores

| Direction | Scores | Why not |
|---|---|---|
| **Off-Register** | 6 / 6 / 5 | Its signature (`--split` from per-claim disagreement) has **no data source and cannot acquire one in this scope** — verified above. Two of three reviewers found this independently. Its own moat argument inverts: it claims a competitor can't copy the split rule without a backend that emits per-claim disagreement, and *this* backend does not emit it either, so the rule reduces to two `box-shadow` insets — a ten-minute port. It also takes all three legs of banlist item 4 (hairline rules universal, zero radius global, a 3-column field with marginalia). **Unsalvageable as a direction.** |
| **VERNIER** | 6 / 6 / 6 | Highest floor, and its accent derivation is the single best argument any direction made (see graft). But its signature, THE SCALE, *already exists in the tree* — `components/layout/PhaseTimeline.tsx` is a sticky per-phase rail with real durations and click-to-scroll, mounted at `app/chat/page.tsx:1200`. A pipeline stepper with per-step timings is the most-shipped element in LLM-ops. And its headline argument is falsified: `--text-subtle #6A716E` on its chassis `#E7EAE7` computes **4.12:1**, below AA, against a claimed 4.55 — so the darker ground it argues *buys* contrast headroom actually spends it. It also flattens `PipelineRail.tsx:114` (the non-converging lanes, the one animation whose every frame is a product invariant) into a 2×2 card grid. |
| **Grade** | 6 / 7 / 5 | Its GRAD-as-confidence idea requires block-level grades. The labels are **inline, mid-sentence** — `demo-run.json` event 7 has a single `content` string carrying VERIFIED, HYPOTHESIS and UNKNOWN, plus ungraded prose. You cannot set a paragraph to `GRAD -30` when it contains a VERIFIED clause, and a span at `GRAD -50` mid-sentence reads as a font-loading glitch. Compounding: `GRAD -60` is outside Roboto Serif's `-50…100` range, stated wrongly in the direction's own two places, and it paid 146 KB to keep the axis. Its mono masthead is the category default it congratulates itself for escaping. |
| **Apparatus** | **7** / 6 / 5 | Highest single score anywhere, on the genericness lens that matters most given the brief. Its thesis — *hue is a data channel spent only on epistemic status; the brand gets none* — is the one move that a competent AI-assisted studio does not make, because deleting the brand colour reads as a career risk. Its fatals are (a) the signature is on the wrong phase, and (b) zero-accent leaves the app with no colour for its own states. **Both are amendable without touching the thesis.** |

### The two amendments

**Amendment A — re-anchor the signature from the synthesis to the critique.**

Apparatus's own product-fit reviewer proposed this as salvage and was right; the data confirms it. The signature is not a gutter down a synthesis. It is:

> **The retained losers.** Four positions, scored across four axes, the rejected ones kept in place and greyed rather than omitted, each carrying the strongest form of the argument the run threw away (`steel_man`), with the judge's own bias flagged as a daggered footnote and a figcaption stating that Total is post-penalty and not the mean.

This is already built — `components/run-record/ScoreMatrix.tsx` — and it is filed on a marketing page. `components/phases/CritiqueCard.tsx` renders **the identical backend data** on the paid surface as a vertical stack of `rounded-[var(--radius-lg)]` bordered articles with `ScoreMeter` bars (`CritiqueCard.tsx:31, 65, 100`), a shape that structurally cannot show the comparison the matrix *is*.

The epistemic gutter survives, relocated to the **perspectives** phase, where 16 labels across 975 words make a marginal column dense enough to read as a profile before you read a word.

**Amendment B — neutralise the accent; do not delete it.**

Apparatus deletes `--accent`, `--accent-hover`, `--accent-text`, `--accent-dim`, `--accent-glow`, `--accent-2`, `--accent-2-dim`. Verified census: 205 `var(--accent)` uses across ~62 files, plus 29 hover, 32 text, 13 dim, 4 glow. That is ~283 per-site judgements, and it strands the app's own states — `PhaseTimeline.tsx` running-phase, the streaming caret, selected conversation, the dashboard quota bar.

The cheaper move that keeps the whole thesis: **set `--accent` to an achromatic value inside the ink ramp.** The token survives as the *interactive role*; it simply has no hue. Zero call-site changes. The site renders with no brand colour, hue is spent only on epistemic status and danger, and if it reads too austere in six months you change one value rather than un-picking 283 sites.

This also fixes the wheel-crowding problem honestly. Five chromatic roles (brand + three epistemic + danger) do not fit on one wheel once the ground family is spoken for. Four do. **That is the real derivation for a hueless accent** — not Apparatus's manufactured claim that a `C 0.008` green-grey ground "makes green unavailable to VERIFIED" (at that chroma nobody reads the ground as green, and it excludes nothing; that argument should be struck from the record).

Cost of Amendment B, stated: with `--accent` achromatic, links stop being distinguishable from body text by colour, so WCAG 1.4.1 requires a persistent underline. The exposure is **33 `text-[var(--accent)]` sites**, not the ~124 one reviewer estimated — I counted by CSS property: 33 `text-`, 11 `bg-`, 55 `border-`, 0 `decoration-`, 0 `ring-`. A one-pass underline sweep on 33 sites is 2–3h and is correct anyway.

---

## 2. GRAFTS

Four discrete elements. Each is nameable, each has a destination, none contradicts "hue is a data channel."

**From VERNIER — the accent derivation, inverted into its stronger form.** VERNIER's rule ("the accent must occupy the one hue band a claim can never occupy, because the run emits green, ochre, slate and red") is the best single argument in all four documents, and its reviewer agreed. Apparatus reaches the same conclusion by a fabricated derivation. Take VERNIER's reasoning and push it one step: there is no free band once the ground takes one and danger takes another, therefore the interactive role gets **no hue at all**. Destination: the `--accent` comment in `tokens.css`, and the `risk` section of this spec.

**From VERNIER — `--warn`/`--ok` are operational tokens today and must be split.** Verified counts: `--ok` 31 uses, `--warn` 22, `--unknown` **4**. The epistemic tokens are overwhelmingly spent on non-epistemic chrome — `settings/page.tsx:130-135` "Encryption Active", `Sidebar.tsx:73` "Memory degraded", `dashboard/page.tsx:123` quota bar, `app/chat/page.tsx:1129-1155` connection dot. `globals.css`'s own comment says these tokens "do nothing else." Make that true. Destination: step 1c of the migration — operational status becomes **ink plus a shape**, not a hue (`PhaseCard.tsx:129` already does this correctly with `CheckCircle2` vs `AlertTriangle`), with `--red` the only survivor. This is a deletion, not an addition.

**From Grade — the epistemic ladder as monotone ink density.** Grade's insight that confidence is a *scalar*, not a set, is right; its execution (font GRAD) is impossible against inline labels. Keep the insight and move it to lightness: VERIFIED darkest and most chromatic, HYPOTHESIS mid, UNKNOWN lightest and least chromatic — a derived ladder rather than three arbitrary hues. Destination: the `--ok / --warn / --unknown` solve targets below (6.40 / 5.20 / 4.60 on the worst legal ground), which produce a monotone 7.46 / 6.03 / 5.32 on `--bg`.

**From Off-Register — nothing.** Its thesis is duplicated by Apparatus's amended signature (the score matrix *is* the disagreement made visible), its palette architecture is worse (two equiluminant peers at 1.2:1 with no primary, which breaks 20+ operational sites), and its four-family font stack costs two non-Google faces and an unbudgeted subsetting pipeline. Grafting from it would be mush. State plainly: it is superseded, not merged.

---

## 3. FATALS — resolved, or named as unresolved

### Apparatus F1 — "The signature has no data on /chat: one label in a 900-word synthesis." **RESOLVED**, and it cost a signature relocation.
Confirmed by my own count (1 label / ~440 synthesis words vs 16 / 975 perspective words). Resolution is Amendment A: the signature becomes ScoreMatrix on the critique phase; the epistemic gutter attaches to the perspectives phase. The synthesis gets **inline** marks via the existing `.epistemic-*` rules, not a margin — which is what `run-record/Segments.tsx:44-52` already does correctly (an inline `<span>` with a 3px left stub carrying the qualifier text).

### Apparatus F2 — "The model-agreement counts (9/9, 4/9, 0/9) are fabricated." **RESOLVED by deletion.**
No such datum exists. Delete the counts. What replaces them in the gutter is real and per-item: `model_used` on each Phase 2 candidate, and `total` + `bias_flags` + `is_top` on each Phase 3 score. The 9rem column narrows to fit what is actually there.

### Apparatus F3 — "Zero accent leaves no colour for success, warning, in-progress, connectivity." **RESOLVED**, at a stated cost.
Amendment B (achromatic `--accent`, token kept) plus the VERNIER graft (operational status → ink + shape + `--red`). Cost: 33 link sites need underlines; the connection cluster at `app/chat/page.tsx:1129-1155` and the quota meter at `dashboard/page.tsx:123` need a shape or a percentage added. ~5h total, and both changes independently satisfy WCAG 1.4.1, which neither site does today.

### Apparatus F4 — "`--alarm` duplicates a token triad that already exists." **RESOLVED.**
Confirmed: `--red`, `--red-bg`, `--red-border` are declared in all base palette blocks with 47 `var(--red)` uses. `--alarm` is struck. Danger is `--red`, and it keeps its existing containment.

### Apparatus F5 (raised by two reviewers) — "The migration surface is 6 palette blocks, not 2." **RESOLVED by counting.**
Verified: `--bg:` is declared at `globals.css` **62, 147, 199, 1020, 1053, 1086** — three base blocks (`:root`, `@media prefers-color-scheme`, `:root.dark`) and three `.invert-band` blocks. Plus three `prefers-contrast: more` selectors at 1240–1265. The token set below is written once and applied to all six, and `tokens.css` exists precisely so that "edit all six" is a single file rather than a scavenger hunt.

### Cross-cutting F6 — "`lib/canvas-fx.ts` silently paints mid-grey on any non-hex token." **RESOLVED, and it must land first.**
Verified at `canvas-fx.ts:26-36`: `if (hex.length !== 6) return '128,128,128'`. An `oklch()` token returns mid-grey with no error and no test. **Therefore the token file below ships hex values as the declared value, with the `oklch()` spec in the comment.** That is the lazy fix — no parser, no call-site change, and the OKLCH stays as the authoring record. `PipelineRail.tsx:56` passes the raw token straight to `fillStyle` and would survive `oklch()`, but the asymmetry is exactly the kind of thing that gets missed in review.

### Cross-cutting F7 — "'Only the wire is missing' between the parser and `/chat`." **UNRESOLVED as stated; re-scoped.**
Verified: `MarkdownRenderer.tsx` is `ReactMarkdown` + `remarkGfm` (mdast). `lib/demo-record.ts` is a bespoke line scanner; `parseSynthesis` (line 222) takes **no arguments** and reads a module-level constant, and neither it nor `parseInline` (line 172) is exported — only types and data consts are. The two halves speak different languages. This is a **new remark plugin**, 10–16h, not a wire. Budgeted as step 4.

### Cross-cutting F8 — "Streaming defeats any parsed epistemic rendering." **UNRESOLVED. Stated cost.**
`StreamingMarkdown.tsx:8-12` says it outright: *"Do NOT use this for live SSE streaming. During active streaming, ChatFeed renders raw text directly to avoid re-parsing the full Markdown AST on every chunk."* So during a run, `[VERIFIED from team size data]` renders as literal square-bracket text and every mark appears at once on completion. **I am not fixing this.** The performance reason is real, and Amendment A moves the signature to the critique phase, which arrives as a single `phase_complete` event and has no streaming problem at all. The synthesis marks pop in at completion; say so in the spec rather than pretending otherwise.

### Cross-cutting F9 — banlist item 4, broadsheet pastiche. **PARTIALLY UNRESOLVED. Named, with a boundary.**
The audit graded the tree PARTIAL (2 of 3 signals) and warned that one more step is the banned one. Apparatus takes that step on both live signals. My correction to the record: `grep -o 'rounded-'` in `components/landing` and `components/run-record` returns **8**, not 0 — and all eight are **controls** (`rounded-[var(--radius)]` on the CTA at `LandingPage.tsx:213`, `CapabilitiesPage.tsx:529`, `DevelopersPage.tsx:422`, `RunRecord.tsx:153,495`; `rounded-[var(--radius-pill)]` on `ApparatusToggle.tsx:114,125`). The zero-radius idiom applies to *cards*, not to *controls*, and it already does.

**Binding boundary, written into this spec:** radius is retained on interactive controls (buttons, pills, fields, switches) and removed from containers. Elevation is carried by a lightness step plus `--border-strong`, not by `shadow-lg`. `columns-` / `column-count` remains forbidden anywhere in `ui-next/src` (verified: currently zero). That gives the system two grouping mechanisms — a hairline and a control silhouette — rather than one, which is the cheapest available defence, and it is stated rather than inherited.

---

## 4. CONCRETE TOKEN SET — `ui-next/src/styles/tokens.css`

Imported from `globals.css` immediately after `@import "tailwindcss"`. `@theme` (fonts) stays in `globals.css` — moving it changes Tailwind v4 resolution order. **Values are hex** so `canvas-fx.ts:30` keeps working (F6); the `oklch()` authoring spec is in the comment.

Ratios were computed, not estimated. Every ink is annotated against **four** grounds, not one, and each declares the grounds it is legal on.

```css
/* ============================================================
   tokens.css — Reasoner colour system

   Hue is a data channel. It is spent on epistemic status
   (--ok / --warn / --unknown) and on danger (--red). It is spent
   nowhere on brand: --accent is achromatic by decision, not by
   omission. Five chromatic roles do not fit on one wheel once the
   ground family and danger are spoken for; four do. If the site
   ever needs a brand hue, it is one value change here — the token
   survives so the 283 accent call sites never have to be touched.

   VALUES ARE HEX ON PURPOSE. lib/canvas-fx.ts:30 returns mid-grey
   for any token that is not 6-char hex, silently, with no test.
   The oklch() spec is the authoring record; the hex is what ships.

   CONTRAST: every ink is annotated against --bg / --surface /
   --surface-2 / --surface-3, and LEGAL names the grounds it clears
   AA on. The previous system annotated against --bg only and shipped
   seven sub-AA pairs; see spec/art-direction.md §0.

   LIGHT IS THE BASE. An unclassed render — SSR before next-themes,
   print, an embed — must be light.

   The dark block is written TWICE on purpose: a media query and a
   class selector cannot share a declaration list. EDIT BOTH.
   The .invert-band blocks in globals.css (lines 1017, 1050, 1083)
   are a THIRD and FOURTH copy. EDIT THOSE TOO — the band redefines
   --accent because a band that swapped only the greys would drop
   its links below AA.
   ============================================================ */

@layer base {
  :root {
    color-scheme: light;

    /* ---- Grounds. Hue 158 at C 0.006–0.013: a green-grey proofing
       stock. Chosen because the two conventional neutral casts are
       taken — warm tan (the borrowed one, ~40deg) and blue slate
       (every dev-tools product). Honest note: three of the four
       explored directions independently landed in 152–168, so this
       is a gap in the market, not an unrepeatable choice.

       --bg drops from oklch 0.977 (ivory) to 0.950. That buys a card
       lift of 1.12:1 where the old #FFFFFF-on-#FAF9F5 was 1.05:1 —
       3x the step, so elevation becomes a tone and --shadow-lg can go.
       It is NOT enough for a boundary (3:1), so --border-strong still
       carries WCAG 1.4.11. Do not claim otherwise.               ---- */
    --bg:             #EBF0ED;  /* oklch(0.950 0.006 158) */
    --surface:        #F9FCFA;  /* oklch(0.988 0.004 158) — 1.12:1 lift over --bg */
    --surface-hover:  #F2F5F3;  /* oklch(0.968 0.005 158) */
    --surface-2:      #E3E9E5;  /* oklch(0.928 0.008 158) */
    --surface-3:      #D9E0DB;  /* oklch(0.900 0.010 158) */

    /* Sidebar keeps its own ramp: hover/active must move toward
       contrast in BOTH themes, which --surface-hover cannot do.
       Unlike the previous system these are no longer within one unit
       per channel of --surface-2/-3 — the rail is a real ground now. */
    --sidebar-bg:     #E4EBE7;  /* oklch(0.934 0.009 158) */
    --sidebar-hover:  #DCE4DE;  /* oklch(0.910 0.011 158) */
    --sidebar-active: #D2DBD5;  /* oklch(0.884 0.013 158) */
    --sidebar-field:  #FCFEFD;  /* oklch(0.995 0.003 158) — inset field on the rail */

    /* ---- Ink. Same hue as the ground at ~2x chroma: ink is the
       ground concentrated, never a foreign grey.
       Annotated  bg / surface / surface-2 / surface-3            ---- */
    --text:        #121814;  /* 15.62  17.43  14.62  13.40  AAA — LEGAL: all grounds */
    --text-2:      #404943;  /*  8.09   9.03   7.57   6.94  AAA — LEGAL: all grounds */
    --text-muted:  #57605A;  /*  5.65   6.30   5.29   4.85  AA  — LEGAL: all grounds
                                 worst case --sidebar-active 4.60 */
    --text-subtle: #606963;  /*  4.93   5.50   4.61   4.23  — LEGAL: --bg, --surface,
                                 --surface-hover, --surface-2, --sidebar-bg, --sidebar-field.
                                 NOT legal on --surface-3 (4.23), --sidebar-hover (4.38),
                                 --sidebar-active (4.01). Use --text-muted there.
                                 Nine grounds cannot carry four AA ink steps in light
                                 mode. The old system pretended otherwise and shipped
                                 five failures; this one declares the restriction. */

    /* ---- Borders: alpha of the opposite ground, never a grey token.
       The alphas below are SOLVED for 3:1, which the old values were
       not: rgb(19 18 17 / 0.26) measured 1.80:1 on --surface, i.e. it
       failed the exact criterion its own comment cited.            ---- */
    --border:        rgb(18 24 20 / 0.14);  /* 1.34:1 — decorative separators only */
    --border-strong: rgb(18 24 20 / 0.47);  /* 3.10:1 on --surface, 3.05:1 on --bg — WCAG 1.4.11 */

    /* ---- Interactive role. Achromatic BY DECISION. See header.
       An ink-filled CTA measures 11.74:1 against its own label —
       ~1.8x the contrast of the coral it replaces (6.54:1), so the
       most important control on every page gets louder, not quieter.
       Links carry a 1px underline at 0.14em offset: with no hue,
       WCAG 1.4.1 requires a second channel. 33 call sites.        ---- */
    --accent:       #2F3832;  /* oklch(0.330 0.016 158) — 10.52:1 on --bg */
    --accent-hover: #1B231E;  /* oklch(0.245 0.015 158) — 13.95:1 on --bg */
    --accent-text:  #F9FCFA;  /* 11.74:1 on --accent */
    --accent-dim:   rgb(47 56 50 / 0.09);

    /* ---- Epistemic labels — VERIFIED / HYPOTHESIS / UNKNOWN.
       These tokens do nothing else, and as of this system that is
       TRUE: operational status (server online, quota, phase result)
       is ink plus a shape, never one of these three.

       The ladder is ink density, not a hue set: confidence is a
       scalar so it is encoded as one. Solved to 6.40 / 5.20 / 4.60
       on --surface-3, the worst ground they render on, which
       produces a monotone 7.46 / 6.03 / 5.32 on --bg.

       Green/amber/grey is the default confidence palette and is
       deliberately not used. Hue separation is 46deg (ok–warn) and
       92deg (warn–unknown); luminance separation is 1.24:1 and 1.12:1.
       That is NOT enough on its own and the system does not pretend
       it is — solid/dashed/dotted at globals.css:982-993 is the
       carrier. Do not restyle those rules.                        ---- */
    --ok:      #2E449F;  /* oklch(0.424 0.150 269)  7.46  8.32  6.98  6.40  AAA */
    --warn:    #7B4193;  /* oklch(0.482 0.140 315)  6.03  6.73  5.65  5.18  AA  */
    --unknown: #2C697D;  /* oklch(0.489 0.070 223)  5.32  5.99  5.02  4.57  AA
                            No longer byte-identical to --text-muted, which is what
                            made an UNKNOWN dot indistinguishable from muted chrome
                            at app/chat/page.tsx:1136,1151. It sits at the same
                            LIGHTNESS as --text-muted by design (it is the quietest
                            rung) and is separated by 65deg of hue and 5x the chroma. */

    /* ---- Danger. The one hue outside the epistemic set. A failed
       request is not a low-confidence claim and the two must never
       be confusable: 25deg is >=70deg from every epistemic hue.   ---- */
    --red:        #AF2A2D;  /* oklch(0.500 0.170 25)  5.71  6.37  5.34  4.90  AA */
    --red-bg:     rgb(175 42 45 / 0.08);
    --red-border: rgb(175 42 45 / 0.22);

    /* ---- Elevation. --shadow-lg is DELETED for containers (elevation
       is a tone now) and RETAINED for floating layers only, where a
       1.12:1 lift cannot say "above unknown ground": Tooltip,
       CommandPalette, UserMenu, modals, Composer, ChatFeed popovers. */
    --shadow:    0 1px 2px rgb(18 24 20 / 0.05), 0 8px 24px -12px rgb(18 24 20 / 0.18);
    --shadow-float: 0 2px 4px rgb(18 24 20 / 0.04), 0 24px 56px -20px rgb(18 24 20 / 0.22);

    --glass-bg:      rgb(249 252 250 / 0.80);
    --glass-bg-soft: rgb(249 252 250 / 0.66);

    /* Scrim darkens in BOTH themes, so it is deliberately not derived
       from --text or --bg (either would invert). */
    --scrim:   rgb(12 16 14 / 0.55);
    --overlay: rgb(12 16 14 / 0.72);

    --background: var(--bg);
    --foreground: var(--text);
  }

  /* System preference — an explicit .light choice must win over it. */
  @media (prefers-color-scheme: dark) {
    :root:not(.light) {
      color-scheme: dark;

      --bg:             #141816;  /* oklch(0.205 0.009 158) */
      --surface:        #1D221F;  /* oklch(0.245 0.010 158) — 1.11:1 lift */
      --surface-hover:  #181D1A;  /* oklch(0.225 0.010 158) */
      --surface-2:      #262C28;  /* oklch(0.285 0.011 158) */
      --surface-3:      #2F3632;  /* oklch(0.325 0.012 158) */

      --sidebar-bg:     #0F1311;  /* oklch(0.183 0.009 158) — rail recedes below --bg */
      --sidebar-hover:  #1D2320;  /* oklch(0.250 0.011 158) */
      --sidebar-active: #2A312D;  /* oklch(0.305 0.012 158) */
      --sidebar-field:  #1D2320;  /* oklch(0.250 0.011 158) */

      /*             bg / surface / surface-2 / surface-3 */
      --text:        #EDF6F0;  /* 16.25  14.64  12.92  11.24  AAA — LEGAL: all */
      --text-2:      #BAC4BE;  /* 10.01   9.02   7.96   6.92  AAA — LEGAL: all */
      --text-muted:  #96A09A;  /*  6.65   5.99   5.29   4.60  AA  — LEGAL: all */
      --text-subtle: #8C948F;  /*  5.76   5.19   4.58   3.98  — NOT legal on --surface-3
                                  or --sidebar-active (4.28). Same restriction as light. */

      --border:        rgb(237 246 240 / 0.13);  /* 1.47:1 */
      --border-strong: rgb(237 246 240 / 0.36);  /* 3.10:1 on --surface — WCAG 1.4.11 */

      --accent:       #C4CFC8;  /* oklch(0.845 0.016 158) — 11.18:1 on --bg */
      --accent-hover: #D9E2DC;  /* oklch(0.905 0.013 158) — 13.53:1 on --bg */
      --accent-text:  #141816;  /* 11.18:1 on --accent */
      --accent-dim:   rgb(196 207 200 / 0.13);

      --ok:      #A2B9FA;  /* oklch(0.793 0.095 269)  9.26  8.35  7.37  6.41  AAA */
      --warn:    #CE90EA;  /* oklch(0.747 0.140 315)  7.51  6.77  5.97  5.19  AAA */
      --unknown: #6AA6BC;  /* oklch(0.693 0.070 223)  6.65  6.00  5.29  4.60  AA  */

      --red:        #FB7D76;  /* oklch(0.733 0.154 25)  7.08  6.38  5.63  4.90  AAA */
      --red-bg:     rgb(251 125 118 / 0.10);
      --red-border: rgb(251 125 118 / 0.26);

      --shadow:       0 1px 2px rgb(0 0 0 / 0.40), 0 8px 24px -12px rgb(0 0 0 / 0.70);
      --shadow-float: 0 2px 4px rgb(0 0 0 / 0.45), 0 24px 56px -20px rgb(0 0 0 / 0.80);

      --glass-bg:      rgb(29 34 31 / 0.78);
      --glass-bg-soft: rgb(29 34 31 / 0.62);
      --scrim:         rgb(0 0 0 / 0.68);
      --overlay:       rgb(0 0 0 / 0.80);
    }
  }

  /* Explicit dark choice — MUST mirror the media query block above
     declaration for declaration. */
  :root.dark {
    color-scheme: dark;
    /* …identical declaration list to the block above… */
  }
}
```

### What changes, by category

**Changes VALUE (19 human-chosen tokens, 0 call sites touched):**
`--bg`, `--surface`, `--surface-2`, `--surface-3`, `--surface-hover`, `--sidebar-bg`, `--sidebar-hover`, `--sidebar-active`, `--sidebar-field`, `--text`, `--text-2`, `--text-muted`, `--text-subtle`, `--accent`, `--accent-hover`, `--accent-text`, `--ok`, `--warn`, `--unknown`, `--red`. Each in six blocks.

**Changes value MECHANICALLY (re-derived, no judgement):**
`--border`, `--border-strong` (alphas re-solved for 3:1 — a correctness fix, not a restyle), `--accent-dim`, `--red-bg`, `--red-border`, `--glass-bg`, `--glass-bg-soft`, `--scrim`, `--overlay`, `--shadow`.

**Changes NAME (1 token, 13 call sites):**
`--shadow-lg` → `--shadow-float`. The rename is the point: it is retained for popovers and forbidden on containers, and a name that says so is cheaper than a review rule. Call sites: `Tooltip`, `CommandPalette`, `UserMenu`, `UpgradeModal`, `ShortcutModal`, `SecurityModal`, `ProvenanceReport.tsx:34`, `Composer`, `Sidebar` ×3, `SiteHeader` ×2, `ChatFeed` ×4 — keep those; strip it from the card sites in `settings/`, `dashboard/`, `pricing/`.

**DELETED (see §6):** `--accent-glow` (4 sites), `--accent-2` / `--accent-2-dim` (2 sites), `--text-small` (0 `var()` uses), `--shadow-lg` on containers.

**UNTOUCHED — mechanism and structure, preserved exactly:**
- `.epistemic-verified / -hypothesis / -unknown` at `globals.css:982-993` — solid / dashed / dotted, 3px left border. Only the three colour values behind them move. This is the signature encoding; the declaration lists do not change.
- The doubled dark block and its "Edit both" instruction; the `light-dark()` future note; light as the unclassed base.
- `@custom-variant dark (&:where(.dark, .dark *))`.
- Borders as alpha of the opposite ground, and the recorded failure of `rgba(160,160,160,0.10)` in the comment.
- The separate `--sidebar-*` ramp and `--sidebar-field`'s reason for existing.
- `prefers-contrast: more` across all three theme selectors (`globals.css:1240-1265`) — **extended**: it currently collapses the ink ramp and leaves `--ok`/`--warn`/`--unknown` alone, which makes the epistemic labels the lowest-contrast text on the page in the mode where a user asked for more contrast. Add the three.
- The entire reduced-motion architecture, 22/22 (`globals.css:1196-1233`, `:728-731`, `:1211-1222`, `:1281`) and every JS loop rendering the FINISHED frame. Nothing here touches it; step 5 only shrinks what it has to govern.
- The 4px spacing scale, 758 token uses, 14 steps.
- The six role-named line-height tokens and the five-step tracking ramp.
- `font-variant-ligatures: none` on `code/kbd/samp/pre`; `tabular-nums lining-nums` on `time/th/td`.
- `--measure: 68ch`, `--width-chat: 48rem`.

### Typography

Three families, all **SIL OFL 1.1**, all on Google Fonts, all reachable through `next/font/google` — **no licence purchase, no manual `@font-face`, no subsetting pipeline.** `fonts.ts:8-12` documents why that matters (next/font emits the size-adjusted fallback that prevents CLS); VERNIER and Off-Register both proposed throwing it away.

| Role | Face | Was | Why |
|---|---|---|---|
| Display (`--font-serif`) | **Piazzolla** (Huerta Tipográfica), variable `wght` + `opsz` | Newsreader | Screen-first Palatino descendant, angular humanist forms, reads as technical monograph not magazine. **Serif is display-only** — which is the inversion that matters: `globals.css:316-317` justifies serif *body copy* in Anthropic's name. Breaking the mechanism is worth more than re-facing it. |
| Body + chrome (`--font-sans`) | **Public Sans** (USWDS / Dan O. Williams), variable `wght` | DM Sans | Libre-Franklin derivative, slightly condensed irregular lowercase — neutral without being Helvetica-neutral. Drawn for documents that must be read by anyone and defended in public. Near-absent from product landing pages. |
| Mono (`--font-mono`) | **Inconsolata** — **unchanged** | Inconsolata | Rung 2 of the ladder: it is already installed, the ligature rule is already written for it, and it is one of the narrowest monos on Google Fonts, which is what a 4×4 score matrix needs. Three of four directions proposed replacing it with Martian Mono, which is a *wider* design — the stated justification ("buys two extra characters per column") inverts. Saves ~60 KB and a decision. |

Above-the-fold preload: two families instead of three (`--font-mono` stays `preload: false` for the reason `fonts.ts` already gives). **Net font payload should be flat to slightly down.**

Type scale: **1.200 minor third, base 16** — `11.1 / 13.3 / 16 / 19.2 / 23 / 27.6 / 33.2 / 39.8`, plus **one** break to 72px for the marketing `h1` (once per route, lint-enforceable). The clamp-as-ratio-compressor mechanism at `globals.css:426-437` is preserved exactly; only the ratio changes from 1.25 to 1.20. This collapses three competing scales into one — verified counts: **291 `var(--text-*)` sites across 40 files, 208 bare Tailwind size utilities across 34 files, 121 `text-[Npt]` / `text-[Npx]` literals across 15 files = 620 sites.** Note `globals.css:23-27` states why the size scale is deliberately not a `@theme` key; converting the 208 bare utilities loses Tailwind's paired line-height, so each needs an explicit `leading-` added. That is why step 7 is the most expensive and last.

---

## 5. MIGRATION PATH

Ordered, independently shippable. Step 1 ships alone and already looks better.

### Step 1 — Palette + the contrast gate · **14–18h** · ships alone
**Changes:** create `ui-next/src/styles/tokens.css` with the above; import from `globals.css` after `@import "tailwindcss"`; apply the same values to the three `.invert-band` blocks (`globals.css:1017, 1050, 1083`) and extend `prefers-contrast: more` (`:1240-1265`) to cover the three epistemic tokens. Hand-mirror the four hardcoded hexes in `app/global-error.tsx:22,41,44,49` (it renders outside the app shell and cannot read the cascade — and `scripts/ci-local.sh:72` explicitly excludes it, so nothing will remind you). Update the five canvas fallbacks in `PipelineRail.tsx:59-63` (currently `'#96401F'` — the coral would survive forever on the one element being promoted), `IdeaField.tsx:100-102`, `DisagreementField.tsx:105-106`. Widen `scripts/check-tokens.sh`'s regex to catch `oklch(` as well as `#hex|rgba?\(`.

Write **`scripts/check-contrast.mjs`**: walk the token block, print the full ink × ground × theme matrix against each token's declared LEGAL set, exit non-zero on any AA failure. ~60 lines. Wire it into `.github/workflows/quality.yml` as **blocking** — today `check-tokens.sh`, the axe spec and Lighthouse are all `continue-on-error: true`, and `lighthouserc.json` only collects `http://localhost:3000`, so `/chat`, `/settings` and `/pricing` are unobserved.

**Visible when it ships:** the two verbatim Anthropic hex values and the self-documented coral derivation are gone in one commit. Cards become visible as tone rather than as a border plus a shadow. Seven existing sub-AA pairs close and `--border-strong` starts satisfying the criterion it cites. `--unknown` stops being `--text-muted`.

### Step 2a — Faces · **2–3h** · ships alone
`ui-next/src/app/fonts.ts` — swap `Newsreader` → `Piazzolla`, `DM_Sans` → `Public_Sans`, keep `Inconsolata`; update the three `@theme` fallback stacks in `globals.css:29-36`. Roles unchanged for now, so zero component edits.
**Visible:** the pairing the census called "the budget version of the thing it copies" is gone.

### Step 3 — Delete the ornament · **4–6h** · net negative lines
See §6. Do this before the expensive steps: it is the cheapest visible improvement left and it removes ~⅓ of a motion vocabulary the app never speaks.
**Visible:** the landing page drops from six orchestrated moments to one; the cursor-following glow (the one verbatim motion banlist hit) goes; `/pricing` loses its shadcn ring-card silhouette with it.

### Step 4 — ScoreMatrix onto `/chat` · **8–12h** · the signature lands
Port `components/run-record/ScoreMatrix.tsx` to replace the card stack in `components/phases/CritiqueCard.tsx` (same backend data: `scores[]` with the four axes, `total`, `bias_flags`, `steel_man`, `is_top`). Rivals across columns, axes down rows, pruned positions greyed **in place** rather than omitted, bias flags as daggered footnotes, figcaption stating Total is post-penalty and not the mean. Delete `ScoreMeter` from `PhaseCard.tsx` if it has no other caller. Give the table its own `overflow-x: auto` container — this is one of the two permitted full-width escapes.
**Visible:** the least imitable thing the product does — showing the dissent the run threw away — stops being a marketing brochure and becomes what you meet after signup. No competitor's backend emits a four-position score matrix.

### Step 5 — Epistemic marks in the run · **10–16h**
Write a remark plugin (`ui-next/src/lib/remark-epistemic.ts`) that matches `\[(VERIFIED|HYPOTHESIS|UNKNOWN)([^\]]*)\]` and emits a node the `MarkdownRenderer` component map renders with the existing `.epistemic-*` classes. Not a wire — `parseSynthesis`/`parseInline` in `demo-record.ts` are unexported and argument-less, and `MarkdownRenderer` is mdast; keep `demo-record.ts` as the run-record path. Attach the marginal gutter to the **perspectives** phase renderer (16 labels / 975 words), inline marks in the synthesis. Marks populate on `phase_complete`, not during stream — state that in the component docblock.
**Visible:** `[VERIFIED from team size data]` stops rendering as square-bracket noise inside a paragraph.

### Step 6 — Role inversion + operational-status split · **10–14h**
Retire serif from body prose (71 `font-serif` / `prose-serif` sites); serif becomes display-only. In the same pass, reassign the ~53 non-epistemic `--ok` / `--warn` uses to ink + shape + `--red`: `settings/page.tsx:83,112,130-135`, `Sidebar.tsx:73`, `PhaseCard.tsx:86,136`, `StatusClient.tsx:32,38`, `dashboard/page.tsx:123,168`, `UsageBadge.tsx:10`, `app/chat/page.tsx:1129-1155`. Add underlines at the 33 `text-[var(--accent)]` sites. De-duplicate `about/page.tsx:37` first (it redeclares `Section`/`Heading`/`Lede`/`Body` instead of importing `prose.tsx`, so every restyle otherwise lands twice).
**Visible:** the epistemic tokens finally do nothing else, which is what their own comment has always claimed.

### Step 7 — Editorial idiom onto the seven generic routes · **12–16h**
`/pricing`, `/security`, `/faq`, `/help`, `/docs`, `/docs/[slug]`, `/settings`. Kill the centred heroes (`pricing:115-118`, `security:92-101`, `faq:43-45`, `help:72-73`), the three-Lucide trust row (`pricing:269-282`), and the tinted icon plate. Free pre-work in the same pass: **define `--space-40`** — it is used at `CapabilitiesPage.tsx:130` and `DevelopersPage.tsx:151` and declared nowhere, so both mastheads currently render behind the 64px fixed header — and fix `CapabilitiesPage.tsx:139` ("Nine mechanisms" over eight §-sections; `app/capabilities/page.tsx:8` metadata says nine too).
**Visible:** the whole surface reads as one product instead of an editorial front door bolted to a template.

### Step 8 — Type scale unification · **16–24h** · last, most expensive
620 sites across three scales. Do it last because every earlier step is independently valuable and this one is pure debt repayment.

**Total: 76–109h.** The first two steps are 16–21h and buy 100% of the banlist escape.

---

## 6. DELETE

Deletion is the design act here — the landing page runs six orchestrated moments where the budget is one.

**Motion / ornament:**
- `components/ui/SpotlightCard.tsx` and its call site at `app/pricing/page.tsx:135-247`. Cursor-following radial glow written from `pointermove` into `--spotlight-x/y` (`SpotlightCard.tsx:96-102`) — the one verbatim motion-banlist hit. Well built; still the banned effect. Its removal takes `/pricing`'s ring-card silhouette down too.
- `IdeaField` (`LandingPage.tsx:608`) — weakest of the three canvases.
- `LogoLoop` marquee (`LandingPage.tsx:262`).
- `ManifestationVisuals.tsx` — self-declared "purely ornamental" at `:23-33`, two infinite loops at 2800/2400ms.
- The plate tilt: `[perspective:1400px]` + `hover:[transform:translateZ(26px)_rotateX(3.5deg)]` at `LandingPage.tsx:541`, `ReviewHandoff.tsx:70,119`.
- `.scroll-grow` (`globals.css:1158`, one call site at `prose.tsx:81`) — a second orchestrated moment, and self-cancelling anyway: its gesture is un-rounding 80px→0, a no-op once container radius is gone.

**Keep and promote:** `PipelineRail` — the only animated element whose every frame is a product fact (`PipelineRail.tsx:114`, `laneOffset` never interpolated toward zero, "these four do not converge"). Take it out of `hidden lg:block` + `aria-hidden` and make it a real exhibit. Do **not** flatten it into a card grid.

**Dead CSS — zero `.tsx` references, verified:**
- `.gradient-text` (`globals.css:926-931`) — a live banlist hit the moment anyone reaches for it.
- `.btn-loading` (`globals.css:854-861`) — the one animated gradient sweep.
- `.hero-heading` (`globals.css:975`) — `text-shadow: var(--accent-glow)`, meaningless once the accent is achromatic.

**Dead components:** `Testimonial.tsx` (no importer; `TESTIMONIALS = []`). Preserve the file's comment as a note in this spec — returning `null` rather than fabricating a quote is the discipline, and it is why nothing in §3 invents a number.

**Tokens:** `--accent-glow` (4 sites), `--accent-2` / `--accent-2-dim` (2 sites), `--text-small` (0 `var()` uses), `--shadow-lg` on containers.

**Emoji as iconography — banlist item 11, verbatim, on the PAID surface.** All four directions missed it. Three files, ~141 lines total: `components/widgets/WeatherWidget.tsx:22` (🌤️), `StockWidget.tsx:23` (📈), `CalculationWidget.tsx:9` (🧮), each inside `<span className="widget-icon">`. Cheapest fix on the board.

**Reset `--dur-scene`.** `globals.css:277` reads `--dur-scene: 600ms; /* route / large transition — 400–800ms */` — the token system sanctioning banlist item 15. Reband it, and route the 18 hardcoded `duration-200/300/500` sites through the tokens so the reduced-motion block governs one surface, not two.

---

## 7. WHAT I COULD NOT DETERMINE — needs a human

**Taste — the display face.** Piazzolla is a defensible, licence-free, uncommon choice, but it is a *choice*, and the strongest objection to every direction here was that its identity-carrying decisions were high-probability. I cannot resolve that from a terminal. **Set Piazzolla, Bodoni Moda and one commercial option side by side at 72px on `#EBF0ED` and pick.** Rejected en route and worth knowing why: Instrument Serif (the 2026 default AI-landing serif), Fraunces (modish), Literata and Source Serif 4 (the standard free substitutes — the same failure mode as the current pairing), and **Redaction** (Kaphar/Betts/MCKL), which is the strongest literal fit — a face whose design axis is halftone degradation — and which I am refusing on the record: it was drawn for a project on the American criminal legal system and carries that subject with it. Borrowing that weight to grade an LLM's confidence would be appropriative, and setting it above a hero reading "Cut headcount before Q3" is the screenshot nobody wants.

**Verify before merge (one command, ~2 min):** that `Piazzolla` and `Public_Sans` are importable from `next/font/google` in the installed Next version with the axes claimed. `npx tsx -e "import {Piazzolla,Public_Sans} from 'next/font/google'"` or grep `node_modules/next/dist/compiled/@next/font/dist/google/font-data.json`. If Piazzolla is absent, the fallback that keeps every other decision intact is **Petrona** (OFL, Google, variable, opsz).

**Budget — nothing.** Every face named is OFL 1.1 on Google Fonts, self-hosted by `next/font`, no attribution in the UI, no traffic banding. This is the one place I diverge sharply from VERNIER, which specified a commercial Dinamo licence with pageview banding. Its argument — "buying the face is what stops it reading as the budget version" — confuses cost with distinctiveness, and it additionally requires committing a purchased `.woff2` to a repo that may be public, which the direction never raised.

**The green-grey convergence.** Three of the four explored directions independently chose a green-grey ground (152 / 158 / 168). I read that as a genuine gap — warm tan and blue slate are both taken — but it is also exactly the kind of convergence the banlist's ten-studios test is designed to catch, and I cannot rule out that it is simply where "not warm, not blue" lands. **A human should look at the step-1 build for ten seconds and say whether it reads as a decision or as an escape.** The token file is one value away from a different cast if the answer is the latter — change hue `158` across the grounds and ink and re-run `check-contrast.mjs`.

**Whether `--warn` at hue 315 (plum) is acceptable for HYPOTHESIS.** It is 46deg from `--ok` and 70deg from `--red`, it clears AA on all four card grounds in both themes, and the dashed rule carries the distinction. But it breaks the amber convention hard, and "unproven" rendered in violet is a taste call. The alternative that keeps everything else is hue 85 (ochre), which costs ~15deg of clearance from the ground family and re-imports a warm residue.

**Backend, explicitly out of scope and worth naming.** The one change that would make every direction here stronger is raising epistemic label density in the Phase 5 synthesis prompt. Today the synthesis emits one label per ~440 words while a Phase 2 perspective emits one per ~61. Nothing in `ui-next/` can fix that, and the amended signature is designed so it does not have to — but if `src/reasoner/phases/` ever gets that change, the marginal gutter becomes viable on the synthesis too, and step 5's plugin already handles it.