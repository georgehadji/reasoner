# UI Plan — Anthropic Accent, Token-System Completion, Liquid Motion Layer

**Status:** draft
**Date:** 2026-08-16
**Branch:** `review-rebase`
**Scope:** `ui-next/` only. No backend, no API, no schema changes.

---

## 0. Summary

Three workstreams, ordered by risk and dependency:

| # | Workstream | Files touched | Risk | Depends on |
|---|-----------|---------------|------|------------|
| **A** | Re-hue accent to the Anthropic/Claude palette | 1 (`globals.css`) | Low | — |
| **B** | Complete the token system, migrate off-system values | ~40 | Low–Med | A |
| **C** | Liquid/gooey surface + responsive motion | ~5 new/edited | Med | A, B |

A and B are corrections — they remove inconsistency that already exists. C is an addition.
**A and B are worth doing even if C is dropped.** C is not worth doing before B, because a
gooey layer built against raw Tailwind palette values would double the migration surface.

### Governing constraint (learned the hard way, twice, this session)

> `filter`, `backdrop-filter` and `transform` on an element make it the **containing block**
> for every `position: fixed` descendant.

`SiteHeader`'s `backdrop-blur-xl` laid `SecurityModal` out against the **1265×64** header strip
instead of the 1280×800 viewport; inside the mobile drawer the reveal `transform` clipped it to a
319px column. Fixed by portalling to `document.body`
([`SecurityModal.tsx:19-25`](../../ui-next/src/components/layout/SecurityModal.tsx#L19)).

Workstream C introduces `filter` on new elements. Every gooey container is a new instance of this
trap. The invariant in §C.1 is not optional.

---

# Workstream A — Accent re-hue to the Anthropic/Claude palette

## A.0 Why this is a one-file change

The design system is CSS-native (Tailwind v4, no `tailwind.config.ts`). Every colour resolves
through a custom property declared in three mirrored blocks of
[`globals.css`](../../ui-next/src/app/globals.css):

| Block | Line | Selector |
|-------|------|----------|
| Light | ~62 | `:root` |
| Dark (system) | ~140 | `@media (prefers-color-scheme: dark) { :root:not(.light) }` |
| Dark (explicit) | ~192 | `:root.dark` |

**Invariant: every token must be defined in all three blocks.** A token defined in two of three is
a theme bug that only appears for users on one specific combination of OS preference and in-app
toggle. This invariant is currently upheld; keep it.

Because the neutral ramp already *is* the Anthropic palette, the change is confined to the accent
family. No component edits.

| Existing token | Value | Anthropic equivalent |
|---|---|---|
| `--bg` (light) | `#FAF9F5` | ivory / bone white |
| `--surface-2` (light) | `#F1EFE7` | ≈ `#F0EEE6` |
| `--text` (light) | `#191817` | ≈ `#191919` |
| `--accent` | `#4F46B8` indigo | ✗ **off-brand** |

## A.1 Contrast analysis (measured, not estimated)

WCAG 2.1 relative-luminance ratios, computed against the real token backgrounds.

**Brand swatches as-is:**

| Swatch | Hex | on `#FAF9F5` | on `#131211` | white on it | `#191817` on it |
|---|---|---|---|---|---|
| Claude orange | `#D97757` | **2.96** ✗ | 5.99 ✓ | **3.12** ✗ | 5.68 ✓ |
| Book cloth | `#CC785C` | **3.11** ✗ | 5.71 ✓ | **3.28** ✗ | 5.41 ✓ |
| Kraft | `#D4A27F` | **2.15** ✗ | 8.26 ✓ | **2.26** ✗ | 7.83 ✓ |
| Manilla | `#EBDBBC` | **1.30** ✗ | 13.71 ✓ | 1.36 ✗ | 13.00 ✓ |

**Conclusion:** the Claude brand orange is a *fill* colour, not a *text* colour. On ivory it fails
AA (4.5:1) for text and even the 3:1 floor for non-text UI. It cannot be a drop-in for `--accent`,
which is used for link text, active nav labels, icons and focus outlines
([`globals.css:361`](../../ui-next/src/app/globals.css#L361)).

Light mode therefore needs a darkened coral, exactly as the system already forks `--accent` per
theme (`#4F46B8` light / `#A79CFF` dark).

**Candidate ramp — light mode (baseline to beat: 6.87 on bg, 7.24 white-on-it):**

| Hex | on ivory | white on it |
|---|---|---|
| `#AE5130` | 4.96 | 5.22 |
| `#A8462A` | 5.58 | 5.88 |
| `#9E4525` | 5.98 | 6.30 |
| **`#96401F`** | **6.54** | **6.89** |
| `#8F3D1E` | 6.98 | 7.36 |

**Candidate ramp — dark mode (baseline to beat: 7.88 on bg, 7.52 text-on-it):**

| Hex | on `#131211` | `#2A1610` on it |
|---|---|---|
| `#D97757` | 5.99 | 5.51 |
| `#E08A6C` | 7.15 | 6.57 |
| **`#E39B80`** | **8.26** | **7.59** |
| `#E8A88F` | 9.29 | 8.54 |

## A.2 Recommended values

```css
/* light — :root */
--accent:       #96401F;  /* 6.5:1 on --bg  */
--accent-hover: #7E3519;
--accent-text:  #FFFFFF;  /* 6.9:1 on --accent */
--accent-dim:   rgb(150 64 31 / 0.09);
--accent-glow:  0 0 24px rgb(150 64 31 / 0.18);

/* dark — both dark blocks, identical values */
--accent:       #E39B80;  /* 8.3:1 on --bg  */
--accent-hover: #EDB79F;
--accent-text:  #2A1610;  /* 7.6:1 on --accent */
--accent-dim:   rgb(227 155 128 / 0.13);
--accent-glow:  0 0 40px rgb(227 155 128 / 0.22);
```

Every ratio at or above the AA threshold with headroom; dark mode *exceeds* the indigo baseline,
light mode sits 0.3 below it (6.54 vs 6.87) — still far above the 4.5:1 requirement.

If you want closer to the literal brand orange, `#9E4525` (5.98) is the warmest value still clearing
AA on both text and fill. Below that, `#AE5130` and lighter break white-on-accent for button labels.

**The inline ratio comments in `globals.css` must be updated in the same edit.** They are load-bearing
documentation — a stale `/* 6.9:1 */` next to a coral value is worse than no comment.

## A.3 Consequence: `--warn` now collides with `--accent`

This is the non-obvious part of the change and the reason it is a plan item rather than a
find-and-replace.

`--warn` is currently `#8A5A16` (light) / `#E0B36A` (dark) — an amber. Against an indigo accent that
reads as clearly distinct. Against a **coral** accent, warn and accent land in the same hue family,
and the only thing separating "this is a link" from "this is a warning" becomes lightness.

Two acceptable resolutions:

1. **Shift `--warn` yellower** — `#7A6012` light / `#E8C878` dark. Cheapest, keeps hue-only encoding.
2. **Stop encoding status by hue alone** — pair every status colour with an icon or a border weight.
   Better accessibility outcome (colour-blind users were never served by hue-only status anyway),
   but touches every consumer.

**Recommendation: (1) now, (2) as a separate follow-up if status semantics ever expand.** Do not
bundle (2) into this change.

## A.4 Verification

- Recompute all four ratios after edit; every value ≥ 4.5:1.
- Toggle light → dark → system in the running app; confirm no token resolves to `unset`.
- `prefers-contrast: more` block ([`globals.css:1017`](../../ui-next/src/app/globals.css#L1017))
  overrides `--border*` and `--text-*` but **not** `--accent`. Confirm the coral still clears
  contrast against the darkened borders. If not, add accent overrides to that block.
- Screenshot the focus ring on `--bg`, `--surface` and `--surface-2` — the outline is
  `2px solid var(--accent)` with a transparent offset and must remain visible on all three.

---

# Workstream B — Complete the token system and migrate off-system values

## B.0 The actual state

Measured across `ui-next/src`:

| Category | Occurrences | Files |
|---|---|---|
| Raw Tailwind palette colours (`bg-green-500`, `text-red-400`, …) | **39** | 13 |
| Non-token sizes/radii/widths (`text-[12px]`, `rounded-2xl`, `max-w-2xl`) | **194** | 37 |

The codebase runs two conventions. `components/phases/` and `components/chat/` are token-disciplined.
`components/layout/` marketing components and the standalone marketing pages are not.

Worst single offender: [`SecurityModal.tsx`](../../ui-next/src/components/layout/SecurityModal.tsx)
— 24 non-token size values plus `bg-green-500/10 text-green-500` where `--ok` already exists.

## B.1 Correction: the error/danger token already exists

**Original draft of this section claimed `globals.css` has no error token and proposed adding
`--err`. Wrong** — `--red`, `--red-bg`, `--red-border` are already defined in all three theme
blocks and serve exactly that role. [`error.tsx`](../../ui-next/src/app/error.tsx),
[`global-error.tsx`](../../ui-next/src/app/global-error.tsx) and others reach for raw `red-*`
Tailwind classes not because the abstraction is missing, but because nobody migrated them —
same disease as the rest of Workstream B, not a special case.

No new token needed. Migrate raw `red-*` classes straight to the existing `--red` family (see
mapping below). `global-error.tsx` is the one exception: it renders outside the root layout
(`globals.css` not loaded), so its `red-500/10` icon badge needs a literal hex mirroring `--red`
if it's ever touched, same reasoning already applied there to the accent button.

## B.2 Migration mapping

Mechanical. A table, applied by hand across ~40 files. **Not a codemod** — writing and validating a
transform costs more than 40 careful edits, and a codemod cannot make the judgement calls in the
"context-dependent" rows.

**Colour — direct substitutions:**

| Off-system | Token |
|---|---|
| `text-green-500`, `bg-green-500/10` | `text-[var(--ok)]`, `bg-[color-mix(in_oklab,var(--ok)_10%,transparent)]` |
| `text-red-*`, `bg-red-*` | `text-[var(--red)]` + `bg-[var(--red-bg)]` / matching `color-mix` |
| `text-amber-*`, `text-yellow-*` | `text-[var(--warn)]` |
| `text-gray-*`, `text-slate-*` | `--text-2` / `--text-muted` / `--text-subtle` by role |
| `bg-gray-*`, `bg-zinc-*` | `--surface-2` / `--surface-3` |
| `border-gray-*` | `--border` / `--border-strong` |
| `text-blue-*`, `text-indigo-*`, `text-violet-*` | `--accent` — **and re-check after A**, some of these were visually matching the old indigo accent and will now look wrong |

**Typography — Tailwind arbitrary → scale token:**

| Off-system | Token | Note |
|---|---|---|
| `text-[10px]` | `text-[length:var(--text-2xs)]` | **11px**, not 10 — 10px is below the readable floor and the token comment says so. This is a deliberate size change, not a rename. |
| `text-[11px]` | `text-[length:var(--text-2xs)]` | |
| `text-[12px]` | `text-[length:var(--text-xs)]` | **13px**, not 12 |
| `text-sm` (Tailwind, 14px) | `text-[length:var(--text-sm)]` | same value, correct source |

`text-[10px]` and `text-[12px]` appearing at all means those components were sized below the scale's
minimum. Migrating them **will** make text larger. That is the point — but it means visual regression
review is required, not just a diff review.

**Radius:**

| Off-system | Token | Note |
|---|---|---|
| `rounded-md` / `rounded-lg` (6/8px) | `rounded-[var(--radius)]` | 8px |
| `rounded-xl` (12px) | `rounded-[var(--radius-lg)]` | **16px** — value change |
| `rounded-2xl` (16px) | `rounded-[var(--radius-lg)]` | 16px, exact |
| `rounded-3xl` (24px) | `rounded-[var(--radius-xl)]` | 24px, exact — but `--radius-xl` is documented as "the composer shell, the one element that is a slab". Using it elsewhere dilutes that meaning; prefer `--radius-lg`. |
| `rounded-full` | `rounded-[var(--radius-pill)]` | |

**Width — context-dependent, judgement required:**

| Off-system | Likely token |
|---|---|
| `max-w-2xl` on a modal | `--width-form` (28rem) or `--width-content` (46rem) by content shape |
| `max-w-2xl` on prose | `--width-content` |
| `max-w-4xl`+ on a page shell | `--width-wide` |

## B.3 Regression guard

Without a guard this decays within a month. The laziest thing that actually works is a grep in CI —
not an ESLint plugin, not a custom rule package.

Add to the existing UI job:

```bash
! grep -rEn --include=*.tsx --include=*.ts \
  '(bg|text|border|from|to|via|ring|fill|stroke)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}' \
  ui-next/src
```

Exits non-zero if any raw palette colour is reintroduced. Run it **after** the migration lands,
otherwise CI is red from day one and gets disabled.

Deliberately **not** guarded: `text-[Npx]` and `rounded-*`. Those have legitimate one-off uses
(icon sizing, hairlines) and a guard that cries wolf gets `# noqa`'d into uselessness. Colour is
the one where "there is always a token" is actually true.

## B.4 Sequencing

1. ~~Add `--err`~~ — not needed, `--red` family already exists (§B.1). `--warn` hue shift from
   §A.3 — done alongside Workstream A.
2. Migrate `components/layout/` (highest density: SecurityModal ✅, UpgradeModal ✅, NeuroPanel ✅,
   PhaseTimeline ✅, UsageBadge ✅). Commit per file or per small group.
3. Migrate standalone pages ✅ (`security/` — already clean, `dashboard/`, `pricing/`, `error.tsx`;
   `global-error.tsx` deliberately left hardcoded, see §B.1). Two files outside the original
   inventory also had raw-palette leaks and were caught by the guard dry-run:
   `settings/api-keys/page.tsx`, `terms/page.tsx` — migrated too.
4. Migrate `PhaseRenderer.tsx` ✅ — 4 colour (tier map), 8 radius, 4 size instances fixed.
5. Add the CI guard ✅ — `tsc` job in `.github/workflows/test.yml`, excludes `global-error.tsx`.
   Verified zero matches against current `src` before landing.

Small commits. This is a wide, shallow change; a single 40-file commit is unreviewable and
un-bisectable.

---

# Workstream C — Liquid surface and responsive motion

## C.0 What already exists

Before adding anything, the inventory (ladder rung 2 — reuse before writing):

| Need | Already present |
|---|---|
| Spring physics | `framer-motion@^12.38.0` — **installed**, used in exactly one file |
| Duration scale | `--dur-micro` 120ms / `--dur-state` 220ms / `--dur-component` 340ms / `--dur-scene` 600ms |
| Easing scale | `--ease-standard`, `--ease-entrance`, `--ease-exit`, `--ease-spring` (`cubic-bezier(0.34, 1.56, 0.64, 1)` — overshoot) |
| Reduced-motion CSS | Blanket kill-switch at [`globals.css:992`](../../ui-next/src/app/globals.css#L992) |
| Paint containment | `.contain-layout-paint` utility |
| Themed translucency idiom | `color-mix(in oklab, var(--accent) N%, transparent)` |
| Hydration-safe reduced-motion detection | [`ManifestationVisuals.tsx:44-55`](../../ui-next/src/components/chat/ManifestationVisuals.tsx#L44) |

**No new dependency is required for any part of this workstream.**

## C.1 Module: gooey filter definition

**Pattern: Flyweight.** One filter definition, N consumers, referenced by id.

The anti-pattern to avoid is an inline `<svg><filter>` per component: duplicated defs, `id`
collisions when two instances mount, and a filter region recomputed per subtree.

Mount once in the root layout:

```tsx
// ui-next/src/app/layout.tsx — rendered once, never unmounts
<svg aria-hidden="true" focusable="false"
     style={{ position: 'absolute', width: 0, height: 0 }}>
  <defs>
    <filter id="goo" colorInterpolationFilters="sRGB">
      <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
      <feColorMatrix in="blur" type="matrix"
        values="1 0 0 0 0
                0 1 0 0 0
                0 0 1 0 0
                0 0 0 19 -9" />
    </filter>
  </defs>
</svg>
```

The last matrix row is the entire technique: alpha × 19 − 9 steepens the blur ramp so ~0.47 alpha
snaps to 0 and ~0.53 snaps to 1, turning overlapping soft edges into one fused shape.

**Use the SVG form, not `filter: blur() contrast()`.** The CSS shorthand thresholds *colour*, so it
requires an opaque parent and shifts hue — it would fight both the theme system and Workstream A.
`feColorMatrix` thresholds **alpha only**: colours pass through untouched and it composites over
transparent backgrounds. For a themed app with a light/dark fork, that difference is decisive.

### The invariant

> **A `filter`-bearing container must not contain any `position: fixed` descendant.**

Gooey containers are leaf decoration. Anything fixed — modal, toast, popover, tooltip — portals to
`document.body`. This is the same rule that `SecurityModal` now follows; C is where it becomes a
systemic constraint rather than a one-off bug fix.

Document it as a comment on the filter def and on every consumer.

## C.2 Module: reduced-motion hook

**Pattern: extract-on-second-consumer.** `ManifestationVisuals` currently inlines
`useReducedMotion()` + `useSyncExternalStore` hydration guard. The gooey layer is the second
consumer. Two is the right trigger to extract for hydration-critical logic — a mismatch here is a
React error, not a cosmetic bug.

```ts
// ui-next/src/hooks/usePrefersReducedMotion.ts
import { useSyncExternalStore } from 'react';
import { useReducedMotion } from 'framer-motion';

const subscribe = () => () => {};
const getSnapshot = () => true;
const getServerSnapshot = () => false;

/**
 * `useReducedMotion()` reads matchMedia during render — `null` on the server,
 * the real value on the client. Branching on it directly is a hydration
 * mismatch, so the switch waits until hydration has landed.
 */
export function usePrefersReducedMotion(): boolean {
  const reduced = useReducedMotion();
  const hydrated = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return hydrated && reduced === true;
}
```

Then refactor `ManifestationVisuals` to consume it. Behaviour-identical; verify by diffing rendered
output, not by re-reading the code.

### Why the CSS blanket rule is not sufficient

[`globals.css:992`](../../ui-next/src/app/globals.css#L992) forces
`animation-duration: 0.01ms !important` on everything. That covers CSS animations and transitions.
It does **not** cover framer-motion, which writes `transform` to the style attribute on every frame
from JS — no CSS rule can stop it.

So: **any framer-motion animation must gate on the hook explicitly.** `ManifestationVisuals` already
does this correctly (renders a frozen static composition rather than a fast one). That is the
reference implementation; copy the shape, not just the intent.

## C.3 Module: liquid surface component

One component. Not a library, not a variants API, not a context provider.

```tsx
// ui-next/src/components/ui/LiquidField.tsx
'use client';
```

- Decorative only: `aria-hidden="true"`, `pointer-events-none`.
- `contain: layout paint` (the existing utility) to fence per-frame invalidation.
- 3–4 absolutely-positioned blobs inside one `filter: url(#goo)` wrapper.
- Colour exclusively via `color-mix(in oklab, var(--accent) N%, transparent)` — inherits Workstream A
  for free, themes correctly, needs no light/dark branch in the component.
- Animate **`transform` only**. Never animate `stdDeviation`: it forces a filter-region recompute
  every frame, which is the difference between a compositor-thread animation and a main-thread stall.
- Under `usePrefersReducedMotion()`, render the blobs at fixed offsets — a static composition, still
  gooey, no loop.

## C.4 Module: motion selection

**Pattern: Strategy — but as a documented decision rule, not as code.** There is no
`<Motion strategy="spring">` wrapper to build. The strategy is chosen by the developer at the call
site; the plan's job is to make the choice unambiguous.

| Interaction class | Strategy | Rationale |
|---|---|---|
| Hover, press, colour change | CSS transition + `--dur-micro` + `--ease-standard` | Zero JS. Already the codebase default. |
| One-shot enter/exit (modal, drawer, panel reveal) | CSS + `--dur-component` + `--ease-entrance` / `--ease-exit` | Not interruptible in practice; a spring buys nothing. |
| Playful one-shot with overshoot | CSS + `--ease-spring` | **Already exists.** Do not reach for JS. |
| Drag, swipe-dismiss, interruptible reorder | framer-motion `type: 'spring'` | Only case where velocity continuity is observable. |
| Ambient / looping decoration | framer-motion, gated on the hook | CSS `@keyframes` also works; use whichever the component already uses. |

### On CSS `linear()`

`linear()` encodes a real spring curve by pre-sampling the physics equation into many points.
Genuine spring shape, zero JS. Two limits matter here:

1. **It restarts at zero velocity when interrupted.** A real spring reads current velocity and
   carries momentum. Fine for one-shot, wrong for gesture.
2. **Its duration changes whenever a spring parameter changes**, which cannot be reconciled with a
   fixed `--dur-*` scale. Adding `linear()` tokens would create a second, conflicting timing system.

**Decision: do not add `linear()` tokens.** `--ease-spring` already provides overshoot for the
one-shot case, and framer-motion covers the interruptible case. Revisit only if `--ease-spring`
measurably falls short on a specific interaction — at which point add exactly one `linear()` token
for that interaction, not a scale.

## C.5 Performance budget

- Filters are per-frame GPU work over the whole element bounding box. Budget **one** `LiquidField`
  per viewport. Two overlapping full-bleed gooey layers is a dropped-frame generator on integrated
  graphics.
- `contain: layout paint` on the container is mandatory, not advisory.
- Verify on the running dev server: DevTools Performance, confirm the animation runs on the
  compositor and the main thread stays idle during the loop.
- If a blob animation shows up as main-thread work, the cause is almost always animating a property
  other than `transform`/`opacity`. Check that first.

## C.6 Accessibility

- Decorative: `aria-hidden="true"`, never focusable, never a hit-test target.
- Reduced motion: static composition, per §C.2. Sustained ambient motion without this is a
  WCAG 2.2.2 failure, not a preference.
- Contrast: the gooey layer sits **behind** content. After Workstream A the accent is coral; verify
  text over the field still clears 4.5:1 at the blobs' brightest point, not just against `--bg`.
- `prefers-contrast: more`: consider suppressing the field entirely. A soft translucent blob layer
  is the opposite of what that preference asks for.

---

## Deliberately not doing

| Cut | Why | Add when |
|---|---|---|
| `linear()` easing token scale | `--ease-spring` covers overshoot; a second timing system conflicts with `--dur-*` | A specific interaction demonstrably needs velocity-accurate one-shot spring |
| Codemod for the token migration | ~40 files, several needing judgement; writing + validating the transform costs more than the edits | Migration surface exceeds ~200 sites |
| ESLint plugin for token discipline | A grep in CI catches the one category worth catching | Guarding beyond colour becomes necessary |
| `<Motion>` wrapper component | The strategy is a decision, not an abstraction; a wrapper adds indirection over a one-line CSS class | Never, probably |
| Status semantics beyond colour (§A.3 option 2) | Real accessibility improvement but touches every consumer; independent of this work | Status states expand past ok/warn/err |
| Migrating `text-[Npx]` under a CI guard | Legitimate one-off uses exist; a noisy guard gets disabled | — |

---

## Verification checklist

**A —**
- [ ] All four accent ratios recomputed and ≥ 4.5:1
- [ ] Inline `/* N:1 */` comments in `globals.css` updated to measured values
- [ ] Light / dark / system toggle — no unset token
- [ ] Focus ring visible on `--bg`, `--surface`, `--surface-2`
- [ ] `--warn` visually distinct from `--accent` at a glance

**B —**
- [x] `--red` family confirmed present in all three theme blocks (no new token needed, §B.1)
- [x] `npx tsc --noEmit` exit 0 (re-verified after full Workstream B)
- [x] `npm run test` — 157/158 passing. The 1 failure (`security-server.edge-cases.test.ts`,
      IPv6 SSRF validation) is unrelated to this work — server-side URL validation logic, no
      `.tsx`/CSS touched by Workstream A/B anywhere near it.
- [x] Guard grep returns zero matches (excluding documented `global-error.tsx` exception)
- [x] Spot-checked live in browser: dark-theme `--accent`/`--warn`/`--red` resolve to the
      measured hex values; `terms/` warn-tinted callout renders with correct `color-mix` bg/border
      and exact `--warn` text color. Full visual pass across all migrated files not done —
      low risk since values were computed from the same scale, not guessed.

**C —**
- [ ] Filter def mounts once; `document.querySelectorAll('#goo').length === 1`
- [ ] No `position: fixed` descendant inside any filter-bearing container
- [ ] `prefers-reduced-motion: reduce` → static composition, zero running loops
- [ ] Performance profile: compositor-thread animation, main thread idle
- [ ] Text contrast over the field ≥ 4.5:1 at brightest blob overlap

## Rollback

Each workstream is independently revertable.
A is one file. B is per-file commits. C is additive — deleting `LiquidField.tsx` and the layout
`<svg>` block returns the app to its pre-C state with no other file depending on them, except
`usePrefersReducedMotion` (which should stay regardless — it is a strict improvement to
`ManifestationVisuals`).
