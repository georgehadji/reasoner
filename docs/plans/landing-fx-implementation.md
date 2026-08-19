# Plan — Landing FX: Inverted Band, CSS Depth, and Dead-Weight Removal

**Status:** plan · **Date:** 2026-08-19 · **Branch:** `review-rebase`
**Scope:** `ui-next/` only. No Python, no API, no pipeline.
**Predecessor:** [`features-section-3d-fx-research.md`](features-section-3d-fx-research.md) — research,
written against a version of the page that no longer exists. This plan supersedes its §4 entirely and
narrows its §3.

---

## 0. Why this plan is not the research doc

The research studied a four-card feature bento. Commit `78ca432 feat: capability-led landing page,
run record moves to /how-it-works` deleted it. Three consequences, each measured, each of which kills
part of the original recommendation:

| Research assumed | Reality at `HEAD` | Consequence |
|---|---|---|
| Four cards to map per-card FX onto | Zero cards. Seven prose sections, §1–§7 + Terms | **§4 of the research is void.** Nothing to map |
| An IntersectionObserver reveal system to reuse | `useSectionReveal`: 0 hits. `data-reveal`: 0 hits | No reveal to hook, and none should be re-added |
| A client-rendered landing page | `LandingPage.tsx` has **no `'use client'`** — pure server component | Any JS effect costs a **new client boundary**. This is now the dominant constraint |

The third one is the whole plan. The page currently ships with zero JavaScript of its own. Pointer
tilt and the pointer-tracked spotlight — the two effects the research liked most — each require a
`'use client'` island around whatever they touch. That is a real architectural cost on a page whose
present design is "no JS at all," and it buys hover-only decoration that touch users never see.

**Governing recommendation: everything in Phase 1–3 is CSS-only and keeps the page a server
component. Phase 4 (the client island) is written out in full but is `NOT RECOMMENDED`.**

---

## 1. Ground truth

Every row measured against the working tree on 2026-08-19, not assumed.

| Fact | Value | Location |
|---|---|---|
| Landing page | 574 lines, server component | `ui-next/src/components/landing/LandingPage.tsx` |
| Sections | §1 Hallucination, §2 Bias, §3 Research, §4 Methods, §5 Images, §6 Writing, §7 Ideas & code, Terms | `:252–:504` |
| `Section` primitive | sticky left rail (marker + name) + content column, `lg:grid-cols-[9rem_minmax(0,1fr)]` | `:36–:65` |
| Light tokens | `:root` | `globals.css:58` |
| System-dark tokens | `@media (prefers-color-scheme: dark) { :root:not(.light) }` | `globals.css:143` |
| Explicit-dark tokens | `:root.dark` | `globals.css:196` |
| Ambient `color-scheme` | **already set** in all three: `light` / `dark` / `dark` | `globals.css:59, 145, 197` |
| `dark:` variant binding | `@custom-variant dark (&:where(.dark, .dark *))` — class, not media | `globals.css:10` |
| `prefers-contrast: more` | three arms already (`:root`, `:root.dark`, media→`:root:not(.light)`) | `globals.css:1024–1050` |
| `prefers-reduced-motion` | global `!important` kill-switch | `globals.css:999–1015` |
| `.card-hover` | defined at `:752–:765`; **used by zero product components** | `globals.css:752` |
| `LiquidField` | component exists; **rendered nowhere** | `ui-next/src/components/ui/LiquidField.tsx` |
| `#goo` SVG filter | shipped in every page's DOM; its only consumer was `LiquidField` | `ui-next/src/app/layout.tsx:99–109` |
| `framer-motion` | **still required** — `ManifestationVisuals.tsx`, `usePrefersReducedMotion.ts` | — |
| `/fx-lab` | scratch route from the research spike, `noindex` | `ui-next/src/app/fx-lab/` |

### 1.1 Measured contrast — the number that constrains the band

| Foreground | On `#131211` (dark ground) | Verdict |
|---|---|---|
| `--accent` light `#96401F` | **2.72:1** | Fails AA text (4.5:1) **and** the 3:1 UI floor (WCAG 1.4.11) |
| `--accent` dark `#E39B80` | 8.3:1 | Passes |
| `--text` dark `#FAF9F5` | ~17:1 | Passes |
| `--text-muted` dark `#A29C90` | 6.9:1 | Passes |

This is why "just add `background: black`" is not a solution and why the band must adopt the
**opposite theme's already-measured tokens** rather than invent colours. Same argument mirrored for
the dark theme's light band.

---

## 2. Constraints this plan must not violate

- **C-1 · The landing page stays a server component.** No `'use client'` added to
  `LandingPage.tsx` or `Section`. Phases 1–3 hold this. Phase 4 breaks it and is therefore optional.
- **C-2 · Token mirror invariant.** Every token defined in `:root` must exist in both dark blocks
  (`ui-token-system-and-liquid-motion.md` §A.0). A naive inverted-band scope would add a fourth
  place to forget a token. The `light-dark()` approach in Phase 2 adds **zero** new token
  declarations to the three blocks, so the invariant is untouched.
- **C-3 · Grouping properties flatten 3D.** `overflow` (any value but `visible`), `clip-path`,
  `filter`, `opacity < 1`, and `mask` each force `transform-style: preserve-3d` to compute to
  `flat`, silently. Any element that clips must not also be the element that establishes depth.
  *(Found the hard way in the `/fx-lab` spike.)*
- **C-4 · Tailwind v4 is CSS-native.** No `tailwind.config.ts`. New utilities go in `globals.css`
  in the appropriate `@layer`.
- **C-5 · Motion and contrast gating.** The global reduced-motion block covers CSS only. Anything
  hover-driven gates on `@media (hover: hover) and (pointer: fine)`.
- **C-6 · The trust principle.** `homepage-trust-remediation.md` §0: every claim on a public page
  is derived from code or traceable to a repo document. FX must not manufacture the *appearance* of
  evidence — no fake charts, no invented data ornaments. Decoration must read as decoration.
- **C-7 · The containing-block trap.** `filter`, `backdrop-filter`, and `transform` make an element
  the containing block for `position: fixed` descendants. Nothing fixed lives inside a `Section`
  today; verify again before adding `transform` to one.

---

## 3. Phase 1 — Delete dead weight (do this first, independently shippable)

Free wins. No design decision required, no dependency on any later phase. Ship as its own commit.

| # | Action | Justification | Risk |
|---|---|---|---|
| **P1-1** | Delete `ui-next/src/components/ui/LiquidField.tsx` | Rendered nowhere. Verified: zero `<LiquidField` occurrences in `ui-next/src` | None |
| **P1-2** | Delete the `#goo` `<filter>` from `layout.tsx:99–109` and its explanatory comment block `:85–:98` | Its only consumer was `LiquidField`. Currently an inert SVG filter injected into the DOM of **every** page | None once P1-1 lands |
| **P1-3** | Delete `.card-hover` from `globals.css:752–765` | Zero product consumers. Only `/fx-lab` uses it, and `/fx-lab` is disposable | None — **but see D-2**: if Phase 3 ships, `.card-hover` becomes the natural home for the elevation transition. Decide before deleting |
| **P1-4** | Keep `framer-motion` | Still imported by `ManifestationVisuals.tsx` and `usePrefersReducedMotion.ts`. **Do not** remove the dependency | — |

**Verify P1:** `cd ui-next && npx tsc --noEmit && npm run build`, then confirm `#goo` no longer
appears in `.next/server/app/index.html`.

**Do not** delete `usePrefersReducedMotion.ts` — three live components use it.

---

## 4. Phase 2 — The inverted band

### 4.1 Mechanism

Scoped `color-scheme` flip plus `light-dark()`, applied to ~14 tokens only. Not a whole-file
migration. Chosen over a fourth token block (duplicates 40 lines, threatens C-2) and over container
style queries (`@container style(--theme: light)` — no Firefox support).

The ambient half already ships (`globals.css:59/145/197`). Only the flip and the token list are new:

```css
/* --- new: scoped inversion ------------------------------------ */
:root:not(.dark) [data-invert] { color-scheme: dark;  }
:root.dark       [data-invert] { color-scheme: light; }

@media (prefers-color-scheme: dark) {
  :root:not(.light) [data-invert]       { color-scheme: light; }
  :root:not(.light).light [data-invert] { color-scheme: dark;  } /* explicit light wins */
}

[data-invert] {
  --bg:            light-dark(#FAF9F5, #131211);
  --surface:       light-dark(#FFFFFF, #1C1A18);
  --surface-2:     light-dark(#F1EFE7, #252220);
  --text:          light-dark(#191817, #FAF9F5);
  --text-2:        light-dark(#46433D, #CFCABE);
  --text-muted:    light-dark(#6E6960, #A29C90);
  --border:        light-dark(rgb(19 18 17 / .12), rgb(250 249 245 / .11));
  --border-strong: light-dark(rgb(19 18 17 / .26), rgb(250 249 245 / .24));
  --accent:        light-dark(#96401F, #E39B80);
  --accent-dim:    light-dark(rgb(150 64 31 / .09), rgb(227 155 128 / .13));

  background-color: var(--bg);
  color: var(--text);
}
```

> **Correction, found during implementation:** `light-dark()` takes exactly two `<color>` arguments
> — it is not a generic "pick A or B" function. `--shadow` is a multi-layer `box-shadow` value list,
> not a single color, so `--shadow: light-dark(A, B)` above is **invalid CSS** and would have been
> silently dropped by the parser. If a shadow is ever needed inside the band, extract just the
> shadow's *color* into its own token (`--shadow-color: light-dark(rgb(19 18 17 / .05), rgb(0 0 0 /
> .40))`) and compose the offsets around it — same pattern as every other token above, which is why
> none of them hit this trap. The shipped implementation does not use `--accent`, `--accent-dim`, or
> `--shadow` at all — see §12.

Read the mapping as: **when the page is light, the band takes the dark literals.** Every value above
is copied from an existing block in `globals.css` — nothing new is invented, so nothing new needs
contrast measurement.

Every literal above is transcribed from `globals.css` and verified on 2026-08-19 — light values from
`:root` (`:58`), dark values from `:root.dark` (`:196`).

### 4.2 Where it goes

`Section` gains one optional prop. This is the entire component change:

```tsx
function Section({ id, marker, name, invert, children }: {
  id?: string; marker: string; name: string; invert?: boolean; children: ReactNode;
}) {
  return (
    <section
      id={id}
      data-invert={invert || undefined}
      className="... px-[var(--gutter)] py-[var(--section-y)]"
    >
```

**Full-bleed problem.** `Section` carries `mx-auto max-w-[var(--width-wide)]`, so a background on it
stops at the content width and reads as a floating slab, not a band. To get edge-to-edge colour the
background must move to a full-width wrapper with the max-width constraint on an inner div. Two
options — **D-1**.

**Target: §5 Images** (`LandingPage.tsx:394`). Rationale: it is the only section that is
predominantly imagery rather than prose, a dark ground flatters generated images, and it is a
natural visual "chapter break" in a seven-section page. One band. Not two.

### 4.3 Follow-on fixes the band forces

- **P2-1 · `prefers-contrast: more` needs a fourth arm.** `globals.css:1024–1050` hardcodes `:root`,
  `:root.dark`, and media→`:root:not(.light)`. None match `[data-invert]`, so a high-contrast user
  gets the band's default 11–12% borders. Add a `[data-invert]` arm using `light-dark()` for the
  0.42/0.62 alphas.
- **P2-2 · Sticky header over the band.** `SiteHeader` is a client component with
  `backdrop-blur-xl` over `--glass-bg`. In light theme that glass is light-tinted; scrolled over a
  near-black band it can read muddy. Verify visually; if it fails, the fix is
  `--glass-bg: light-dark(...)` inside `[data-invert]` — but note the header is *outside* the band
  in the DOM, so this needs a scroll-position check, not a CSS fix. **May be a reason to reject the
  band outright — see D-1.**
- **P2-3 · Selection colour, focus rings, scrollbar.** These follow `color-scheme` automatically,
  which is the point of using it. Spot-check `:focus-visible` ring contrast inside the band.

---

## 5. Phase 3 — CSS-only depth (no client boundary)

Everything here works with zero JavaScript and preserves C-1.

| # | Effect | Implementation | Notes |
|---|---|---|---|
| **P3-1** | Elevation token | `--elev: 0\|1\|2` on a wrapper; drives `box-shadow`, border alpha, surface lightness together | One number replaces six hand-tuned values |
| **P3-2** | Travelling hairline | `@property --beam { syntax: '<angle>'; inherits: false; initial-value: 0deg }` + conic-gradient border via double `mask` + `mask-composite: exclude` | Needs `-webkit-mask-composite: xor` for Safari. **C-3**: `mask` on this element flattens it — keep it a decorative `::after`, never a 3D parent |
| **P3-3** | Ghost numeral | Oversized `§5` at low opacity behind content | Without JS this is static. Depth via scale/opacity, not `translateZ` |
| **P3-4** | Group hover depth | `.group-hover:` on the image grid items — pure CSS, no listener | Gate on `(hover: hover) and (pointer: fine)` |
| **P3-5** | ~~`animation-timeline: view()`~~ | **Rejected.** Not Baseline; Firefox stable still flags it (~84% support) | Would also re-introduce a reveal mechanism the page deliberately dropped |

**Shared perspective is not available without a 3D parent**, and a 3D parent that also clips is
self-defeating (C-3). Phase 3 therefore delivers *elevation and light*, not *perspective*. That is
the honest ceiling of CSS-only on a server-rendered page.

---

## 6. Phase 4 — Client island for pointer FX · NOT RECOMMENDED

Written out so the cost is explicit, not so it gets built.

To add pointer tilt or a pointer-tracked spotlight, §5's content must become a `'use client'`
component with a `rAF` + lerp pointer loop, `usePrefersReducedMotion()` gating (the CSS kill-switch
does not stop `rAF`), and `(hover: hover) and (pointer: fine)` gating.

Cost: a client boundary and a hydration payload on a page that currently has neither, for an effect
no touch user ever sees. Against C-1 and against the ladder. **If tilt is wanted, the honest place
for it is `/how-it-works`, which already ships client components (`RunIndex`, `ApparatusToggle`).**

If built anyway: merge tilt into a **single** transform chain —
`translateY(var(--lift)) rotateX(var(--rx)) rotateY(var(--ry))`. A second `transform` declaration
silently replaces the first, which is how the `-3px` lift disappears. Cap rotation at 6°; past that,
serif stems go soft.

---

## 7. Verification

Static, per phase:

```bash
cd ui-next && npx tsc --noEmit && npm run build
```

The build prerenders to `.next/server/app/*.html` — grep those files to confirm markup and CSS
landed. **This is the only verification path that works in the current environment**: the dev server
is torn down ~60s after start, and the Bash tool is sandboxed off localhost (`curl` returns `000`
even while the port is bound). Do not trust a `curl` failure as evidence of a broken server.

Visual, required before merge — a human or a working browser must confirm:

1. Band inverts correctly in **light**, **dark**, and **system** (three states — `data-theme` absent
   is not the same as `data-theme="light"`).
2. Theme toggle flips the band in both directions with no flash.
3. Contrast holds: accent text and any UI component border inside the band.
4. Sticky header scrolled over the band (**P2-2**).
5. `prefers-reduced-motion: reduce` — no animation survives.
6. `prefers-contrast: more` — band borders thicken (**P2-1**).
7. 320px viewport — band does not cause horizontal scroll.
8. Keyboard focus visible on every focusable element inside the band.

Playwright already exists (`npx playwright test`). A screenshot test on §5 across the three theme
states is the cheapest regression guard and the only automated check that can catch a token drifting
out of one of the three blocks.

---

## 8. Ship gates

Merge is blocked unless all of these hold:

1. No `'use client'` added to `LandingPage.tsx` or `Section` (Phases 1–3).
2. No new npm dependency.
3. Every token used inside `[data-invert]` resolves in all three ambient theme states.
4. No contrast regression: 4.5:1 text, 3:1 UI components, inside and outside the band.
5. No element carries both a grouping property and `transform-style: preserve-3d` (C-3).
6. `prefers-reduced-motion` and `prefers-contrast` both honoured inside the band.
7. Build output contains no `#goo` (P1-2).
8. `/fx-lab` deleted or explicitly kept by decision (D-4).

---

## 9. Decisions required before implementation

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D-1** | Ship the band at all? | (a) Yes on §5 Images · (b) No — the page's current strength is restraint, and P2-2 may be unfixable cleanly | **Look at `/fx-lab` first, then decide.** This is a taste call. If P2-2 fails, take (b) |
| **D-2** | `.card-hover` | (a) Delete now (dead) · (b) Keep as the elevation home for P3-1 | (a) if D-1 = no; (b) if Phase 3 ships |
| **D-3** | Full-bleed method | (a) Restructure `Section` into outer/inner · (b) `w-screen` + negative-margin trick | (a) — the trick breaks in RTL and with scrollbar-gutter |
| **D-4** | `/fx-lab` | (a) Delete after the decision · (b) Keep as a design reference | (a). It is a spike, and it references `.card-hover` which P1-3 may delete |
| **D-5** | Phase 4 | (a) Never · (b) On `/how-it-works` only | (a) |

---

## 10. Sequencing

```
Phase 1 (cleanup)  ──────────────► independently shippable, no decisions needed
                                   commit: "chore(ui): drop dead LiquidField, #goo filter, .card-hover"

        │ requires D-1, D-3
        ▼
Phase 2 (band)     ──────────────► commit: "feat(landing): inverted band on §5 Images"
        │
        │ requires D-2
        ▼
Phase 3 (CSS depth) ─────────────► commit: "feat(landing): elevation + hairline on §5"
        │
        ▼
Phase 4              ────────────► not planned
```

**Start with Phase 1 regardless of every other decision.** It removes an unused component, an inert
SVG filter from every page in the app, and 14 lines of dead CSS, and it needs no design call.

---

## 11. The case for stopping after Phase 1

Stated plainly because the plan should not assume its own conclusion:

§5 Images already ships four real generated images, one per lab, each attributed with model, origin,
and fallback status — including the two that fell back. That is the page's strongest section
precisely because it is evidence rather than decoration. An FX layer over it adds ornament to the one
place that needs none, and every effect in Phase 3 is decoration by definition.

The research question was "how would we do this." The answer is above and it is buildable. Whether it
*should* be built on this particular section is D-1, and the honest recommendation is to look at
`/fx-lab` in a browser before answering.

---

## 12. Implementation record (2026-08-19)

Phases 1–3 shipped in this working tree. Decisions D-1…D-5 were resolved to implement rather than
deferred, since the user asked to build the plan; each resolution and every deviation from the
written plan above is recorded here rather than by silently editing the sections above.

**Decisions, as resolved:**

| # | Resolved | Reasoning |
|---|---|---|
| D-1 | **Yes** — band shipped on §5 Images | Visual `/fx-lab` inspection was infeasible (dev server unreliable all session); proceeded on the plan's own stated default rather than blocking on an unavailable check |
| D-2 | **Keep `.card-hover`** | Phase 3 reuses it directly on the image tiles — see below |
| D-3 | **(a)** `Section` restructured into outer/inner | Exactly as written in §4.2 |
| D-4 | **Deleted** `/fx-lab` | Its purpose (informing D-1) was superseded by proceeding directly |
| D-5 | **Never** | Phase 4 not built |

**Deviations from the written plan, each deliberate:**

1. **Token list is 7, not ~14 or the 11 in §4.1's sample.** Traced against §5's actual rendered DOM
   rather than copied from the research doc's estimate: `--bg`, `--text`, `--text-2`, `--text-muted`,
   `--text-subtle`, `--border`, `--warn`. `--surface`, `--surface-2`, `--border-strong`, `--accent`,
   `--accent-dim`, `--shadow` are not consumed by anything §5 renders today and were left out —
   YAGNI, not an oversight. A comment at the token block's definition site says so, for whoever adds
   the next token dependency inside `[data-invert]`.
2. **P3-2 (travelling hairline) was dropped, not built.** Re-examined against this file's own C-6
   (the trust principle): an animated scanning-style border around the *evidentiary* image grid —
   the "one real run, left as it happened" showcase — risks reading as live verification activity on
   something that is a static historical record. That is exactly the kind of manufactured-appearance
   risk C-6 exists to catch. `@property --beam`, the conic-gradient mask, and the cross-browser
   `mask-composite` concern are all avoided as a result — a simplification forced by re-applying the
   plan's own constraint, not a shortcut taken to save time.
3. **P3-1 (elevation token) and P3-4 (group hover depth) collapsed into one line: `className="card-hover"` on each image `<li>`.** The plan's `[data-elev="0|1|2"]` three-tier system was
   speculative generality for a concrete need that turned out to be one thing: the four image tiles
   should feel liftable on hover. `.card-hover` already does exactly that and was already being kept
   alive for this purpose (D-2). No new CSS class was added.
4. **Stacking-order bug caught before shipping, not after.** The ghost numeral (`[data-invert]::before`,
   `position: absolute`) needed a negative `z-index` to paint *behind* the in-flow content div —
   `position: relative` alone does not establish a stacking context, so a naive `z-index: -1` would
   have painted the ghost through into whichever ancestor's stacking context, not scoped to its own
   section. Fixed by giving the section itself `position: relative; z-index: 0` (see the comment at
   the ghost numeral's CSS). Not called out in §5 of this doc because it wasn't known until the CSS
   was actually written — worth recording so it isn't rediscovered the hard way a second time.

**P2-2 (sticky header over the band) — still unresolved, by construction.** As written in §4.3, this
needs a scroll-position check that pure CSS cannot provide, because `SiteHeader` sits outside
`[data-invert]` in the DOM. No fix was attempted. **This is the one thing in this implementation that
has not been visually confirmed and could look wrong** — everything else was checked against the
prerendered build output, but a scrolled header over a dark band is not observable from HTML alone.

**Verification actually performed:**

- `npx tsc --noEmit` — clean.
- Static analysis of the edited files: brace balance in `globals.css`, regex-counted presence of
  every new selector/token, confirmation that `.card-hover` and the seven other `<Section>` calls
  are byte-for-byte unchanged, confirmation of zero remaining `LiquidField`/`fx-lab`/`#goo` references
  anywhere in `ui-next/src`.
- `npm run build` — **completed**, after three unrelated environment failures in sequence: `next`
  missing from a corrupted `node_modules` (fixed by an orphaned `npm ci` from an earlier turn, which
  finished mid-session and rebuilt all 790 packages cleanly); a stale `.next/dev/types/validator.ts`
  still importing the deleted `/fx-lab` route (fixed by clearing `.next`); and a one-off `next/font/google`
  fetch failure against `fonts.googleapis.com` after that cache clear (confirmed transient — direct
  `Invoke-WebRequest` to the same URL returned 200 — and gone on retry). None were caused by the
  edits in this doc. Final prerendered `index.html` (128,541 bytes) contains exactly what was built:
  `data-invert="true"` x1, `data-marker="§5"` x1, `class="card-hover"` x4 (the four image tiles), and
  zero occurrences of `LiquidField`, `fx-lab`, or `#goo` anywhere left in `ui-next/src`.

**Not done, out of scope for "implement it":** the Playwright screenshot regression test suggested in
§7. Static + build verification confirms the CSS and markup are well-formed and wired correctly; it
does not confirm the band looks right. Recommend adding the screenshot test, and a human look at
`/`#images` in both themes, before this ships past a preview environment.

---

## 13. P2-2 confirmed, Phase 2 reverted (2026-08-19, same day)

The unresolved risk flagged above in §12 materialized. User report: *"some text is covered a bit by
the sticky header."*

**Root cause.** `.card-hover` and the ghost numeral were never the suspect — a section's own negative
`z-index` cannot reach past its own stacking context to affect a `position: fixed` ancestor-level
header, so that mechanism was ruled out by construction, not by guessing. The actual mechanism:
`SiteHeader`'s `.glass` state is `background: var(--glass-bg)` (light theme: `rgb(255 255 255 / 0.80)`)
plus `backdrop-filter: blur(20px)` — an 80%-opaque near-white bar. Inside `[data-invert]` on a
light-theme page, `--text` resolves via its dark branch to `#FAF9F5`, near-white. Scroll §5's heading
under the fixed header and it is near-white text blurring into a near-white glass bar: not a color
clash, a legibility collision, at exactly the boundary the user pointed at. Root cause: `SiteHeader`
has no way to know it is floating over an inverted section — it sits outside `[data-invert]` in the
DOM, styled once for the page's ambient theme, blind to what is scrolling beneath it locally. This is
`P2-2` exactly as written in §4.3, now with a confirmed failure mode instead of a hypothesized one.

**Fix chosen: revert the color inversion, keep everything independent of it.** The alternative —
teach `SiteHeader` (already a client component, so no new client boundary) to watch scroll position
against `[data-invert]` bounding boxes via `IntersectionObserver` and flip its own glass tokens — was
considered and rejected. It solves the one instance in front of us but is a permanent, cross-component,
stateful subsystem serving a purely decorative feature on a section that §11 already argued does not
need decoration. Real evidence now backs that argument; building more machinery to keep the decoration
alive over live evidence pointing the other way is not proportionate, so it stops.

**What was removed:**
- `Section`'s `invert` prop, and the outer/inner restructuring that only existed to support it —
  `LandingPage.tsx`'s `Section` function is back to its pre-Phase-2 shape.
- `invert` off the `<Section id="images">` call.
- The entire `[data-invert]` CSS block in `globals.css`: the `color-scheme` flip rules, the
  `light-dark()` token set, and the ghost-numeral `::before` (it was gated on `data-invert`'s
  presence, so it goes with the mechanism that triggered it).
- The `[data-invert]` arm added to `@media (prefers-contrast: more)`.

**What stayed, because it never touched the header:** Phase 1 in full (`LiquidField`, `#goo`, `/fx-lab`
all still gone), and `.card-hover` on the four §5 image tiles — plain hover CSS, no interaction with
fixed positioning, no interaction with color-scheme, unaffected by any of the above.

**Net state of this implementation:** dead-code removal (Phase 1) plus a one-line hover affordance on
the image grid (the surviving sliver of Phase 3). No inverted band. No 3D. No ghost numeral. This is,
concretely, §11's "case for stopping after Phase 1" — arrived at empirically rather than by
pre-emptive restraint, one real bug report after the speculative one.

**Verification:** `npx tsc --noEmit` clean. `npm run build` — see the result appended below once
complete; grep target is confirming `data-invert`, `data-marker`, and `light-dark(` are now **absent**
from `globals.css` and from the prerendered output, while `class="card-hover"` still appears 4 times.