# Research — Features Section: Inverted Band, 3D/FX Treatment, and Generated Imagery

**Status:** research · **Date:** 2026-08-17 · **Branch:** `review-rebase`
**Scope:** `ui-next/` only — the four-card feature bento in
[`LandingPage.tsx:53-82`](../../ui-next/src/components/landing/LandingPage.tsx#L53) and
[`:486-536`](../../ui-next/src/components/landing/LandingPage.tsx#L486).
**Deliverable:** options, costs, and failure modes.

**Two updates since first writing (2026-08-18).**
1. The section this doc studies **no longer exists in the working tree.** It is still in `HEAD`, but
   the uncommitted `LandingPage.tsx` rewrite replaced the feature bento with a real-run record, on
   the stated reasoning that cards *describe* the product where a record *demonstrates* it. Line
   references above point at `HEAD`. The inverted-band mechanism (§2) and the shared FX layer (§3)
   transfer to any section; only the per-card mapping in §4 is tied to the cards.
2. A working lab of every effect here now exists at
   [`ui-next/src/app/fx-lab/`](../../ui-next/src/app/fx-lab/FxLab.tsx) (route `/fx-lab`, noindex,
   no new dependencies, deletable in one `rm -r`). Corrections found while building it are marked
   **Correction** inline.

---

## 0. Summary

Three questions were asked. Short answers first:

| Question | Answer |
|---|---|
| How to invert the band (dark in light theme, light in dark)? | Scope `color-scheme` + a token override to the `<section>`. Reuse the **already-measured opposite-theme tokens** rather than inventing new colours. §2 |
| How to present it with 3D/FX? | Shared `perspective` on the grid + **per-card FX that means the card's content**, not four identical tilts. Pointer-spotlight and depth-layering are the highest yield per byte. No WebGL. §3–4 |
| What AI-generated images can be used? | Non-representational abstraction only. On a section whose entire claim is "we don't fabricate", a photoreal render or a fake dashboard is a self-inflicted wound. Line-art SVG beats raster on every axis here. §6 |

### The one concern worth stating before anything is built

`docs/plans/homepage-trust-remediation.md` §0 sets the governing principle for this surface:

> Every number, badge, and guarantee on a public page must be either (a) derived from code at build
> time, or (b) traceable to a document in this repo.

FX and imagery are not claims, so they are not directly covered — but the *section* is the trust
argument, and the visual register is part of how it is read. An "AI landing page" visual vocabulary
(glowing brain, neural mesh, humanoid robot, holographic HUD) reads as generic and undercuts a
section arguing for epistemic rigour. That is a taste judgement, not a rule, and it is stated once
here rather than repeated. Everything below is designed to be spectacular *and* sober.

---

## 1. Ground truth — what the code already constrains

Measured from the current tree, not assumed.

| Fact | Source | Consequence |
|---|---|---|
| Tailwind v4, CSS-native tokens, **no** `tailwind.config.ts` | `globals.css:1-36` | All FX are custom properties + `@layer utilities`. No config file to extend. |
| Colour tokens live in **three mirrored blocks** — `:root`, `@media (prefers-color-scheme: dark) :root:not(.light)`, `:root.dark` | `globals.css:58`, `:143`, `:196` | Invariant from the UI plan §A.0: a token defined in two of three is a theme bug. An inverted band must not become a fourth unmirrored block. |
| `--accent` light = `#96401F`, dark = `#E39B80` | `globals.css:97`, `:167` | See §2.3 — the light accent **fails** on a dark ground. |
| Global `prefers-reduced-motion` kill-switch uses `!important` on `animation-duration`/`transition-duration` | `globals.css:999-1015` | Covers CSS animation only. A rAF loop or a framer-motion `animate` prop is **not** covered and must be gated in JS. |
| `prefers-contrast: more` block re-declares borders/text | `globals.css:1024-1040` | An inverted band needs its own entry here or it silently keeps 11%-alpha borders. |
| `usePrefersReducedMotion()` hook exists and is already used | `LiquidField.tsx:93` | Reuse it. Do not add a second detector. |
| `#goo` SVG filter is a **single global instance** in the document | `layout.tsx:99-109` | Shared. Reusable, but see §3 T3 — the hero already owns the gooey budget. |
| `filter` / `backdrop-filter` / `transform` make an element the containing block for `position: fixed` descendants | UI plan §0, learned twice | Any `perspective`/`transform` wrapper on the features band inherits this trap. The band has no fixed descendants today; that is a fact about today, not a guarantee. |
| Grid is `auto-fit` `minmax(min(100%, 320px), 1fr)`, container queries at **664px** and **1008px**, cards laid 2+1+1+2 | `LandingPage.tsx:42-51` | Adding imagery changes intrinsic card height. The 2+1+1+2 rhythm only stays whole-rowed if the wide and narrow cards keep proportional heights. |
| Reveal is IntersectionObserver-driven with a `<noscript>` escape hatch | `LandingPage.tsx:265-289`, `:335-341` | Any scroll-driven CSS added on top is a *second* mechanism, not a replacement. See §3 T0-5. |
| `.card-hover` already applies `translateY(-3px)` on hover | `globals.css:752-765` | A tilt transform must be merged into one chain with it, not stacked as a second `transform` declaration (the last one wins and silently kills the lift). |
| Deps: framer-motion 12, next-themes, lucide. **No** three.js, no GSAP | `package.json:15-36` | WebGL is a new dependency decision, not a free one. |

---

## 2. The inverted band

### 2.1 Three mechanisms

**A — Scoped token override.** `[data-invert]` re-declares the ~14 tokens the section uses, with the
opposite theme's literals. Needs one rule per ambient theme (light→dark, dark→light, plus the media
variant), because a bare `[data-invert]` cannot know which theme it is inside.

*Ships today. Zero new platform features. Verbose — it grows the mirrored-block count from 3 to 6.*

**B — `light-dark()` + scoped `color-scheme`.** Each token declared **once** as
`light-dark(lightValue, darkValue)`; the band flips `color-scheme` and every token follows.
`light-dark()` is Baseline (Chrome 123+, Safari 17.5+, Firefox 120+). `globals.css:54-55` already
names this as the intended future simplification.

*Cleanest. But converting all ~40 tokens is a Workstream-B-sized change, not a section change.*

**C — `--theme` sentinel + container style queries** ([Dave Rupert, 2026-04](https://daverupert.com/2026/04/inverted-light-dark/)):

```css
:root { color-scheme: light dark; --theme: light; }
@media (prefers-color-scheme: dark) { :root { --theme: dark; } }
[data-theme="light"] { --theme: light; }
[data-theme="dark"]  { --theme: dark;  }

@container style(--theme: light) { [data-theme="inverted"] { --theme: dark;  } }
@container style(--theme: dark)  { [data-theme="inverted"] { --theme: light; } }
```

Most elegant, and it **nests** — an inverted thing inside an inverted thing flips back correctly.
Cost: container style queries are Chromium + Safari only; Firefox does not ship them (planned 2026).
Needs a fallback path, which is mechanism A anyway.

### 2.2 Recommendation

**B, scoped narrowly.** Do not migrate the whole token file. Convert only the tokens this band
touches to `light-dark()`, then invert with three one-line rules instead of three 40-line blocks.

*Verified against the code after this doc was first written:* the **ambient** half already ships —
`globals.css:59` sets `color-scheme: light`, `:145` and `:197` set `dark`. So the ambient block below
is existing behaviour reproduced for context, and the only genuinely new CSS is the `[data-invert]`
flip plus the token list.

```css
/* Ambient scheme, driven by the class (next-themes), not the media query alone. */
:root                                        { color-scheme: light; }
:root.dark                                   { color-scheme: dark;  }
@media (prefers-color-scheme: dark) {
  :root:not(.light)                          { color-scheme: dark;  }
}

/* The band takes the opposite of whatever it is inside. */
:root:not(.dark) [data-invert]               { color-scheme: dark;  }
:root.dark       [data-invert]               { color-scheme: light; }
@media (prefers-color-scheme: dark) {
  :root:not(.light) [data-invert]            { color-scheme: light; }
  :root:not(.light).light [data-invert]      { color-scheme: dark;  } /* explicit-light wins */
}
```

Then, for the band's tokens only:

```css
[data-invert] {
  --bg:            light-dark(#FAF9F5, #131211);
  --surface:       light-dark(#FFFFFF, #1C1A18);
  --text:          light-dark(#191817, #FAF9F5);
  --text-muted:    light-dark(#6E6960, #A29C90);
  --border:        light-dark(rgb(19 18 17 / .12), rgb(250 249 245 / .11));
  --border-strong: light-dark(rgb(19 18 17 / .26), rgb(250 249 245 / .24));
  --accent:        light-dark(#96401F, #E39B80);
  --accent-dim:    light-dark(rgb(150 64 31 / .09), rgb(227 155 128 / .13));
  --shadow:        light-dark(
                     0 1px 2px rgb(19 18 17 / .05), 0 8px 24px -12px rgb(19 18 17 / .18),
                     0 1px 2px rgb(0 0 0 / .40),    0 8px 24px -12px rgb(0 0 0 / .70));
  background: var(--bg);
  color: var(--text);
}
```

Because `color-scheme` on the band is already flipped, `light-dark()` inside it resolves to the
opposite theme's values automatically. **No new colours are invented** — every literal above is
copied from an existing, already-contrast-measured block.

### 2.3 The five gotchas that make naive inversion fail

1. **Accent contrast collapses.** `--accent` light `#96401F` on the dark ground `#131211` measures
   **2.7:1** — fails AA text (4.5:1) *and* fails the 3:1 UI-component floor of WCAG 1.4.11. The band
   must take `#E39B80` (8.3:1, already measured in `globals.css:167`). This alone is the reason
   "just set `background: black`" is not a solution.
2. **Shadows do not invert themselves.** Light `--shadow` is dark ink at 5%/18% alpha — on a
   near-black ground it is invisible, and the featured card loses its lift entirely.
3. **`color-scheme`, not just colours.** Scrollbars, `<select>` popups, autofill, and the caret all
   follow `color-scheme`. This band has no form controls today; setting it is still correct and
   costs one declaration.
4. **`prefers-contrast: more` does not follow.** `globals.css:1024` hardcodes the light and `.dark`
   selectors. The band needs its own entry or high-contrast users get 11%-alpha borders on a black
   field.
5. **The glass header fights the band.** `SiteHeader` is sticky with `backdrop-blur-xl` over
   `--glass-bg` (a *light* translucent white in light theme). Scrolling a black band beneath it
   turns the header into a muddy grey strip. Either accept it, or give the header a
   `--glass-bg` that samples via `color-mix` — worth a look before shipping, not a blocker.

### 2.4 Edges

The section is a root-level `<section>` inside a full-width `<main>`, with padding applied per
section — so full-bleed costs nothing structurally: move `px-[var(--gutter)]` onto an inner
wrapper and put the background on the `<section>`.

The `<Rule />` separators that currently bracket this section
([`LandingPage.tsx:480`](../../ui-next/src/components/landing/LandingPage.tsx#L480),
[`:538`](../../ui-next/src/components/landing/LandingPage.tsx#L538)) become redundant — a hairline
against a hard tonal edge reads as a doubled line. Delete them for this section only.

Edge treatment options, in order of fit with the existing editorial language:
1. **Hard full-bleed edge.** Honest, magazine-like, matches the serif/Rule vocabulary. Recommended.
2. **Inset slab** with `--radius-xl` and `--space-8` side margins. Reads as a component, not a
   chapter. Weaker.
3. **Gradient bleed** into `--bg`. Softens the transition but makes the top/bottom ~80px of the band
   an unusable contrast gradient. Avoid — text near a gradient edge cannot be contrast-guaranteed.

---

## 3. FX menu, tiered by cost

### T0 — CSS only, no new tech

**T0-1 · Elevation as a token, not a hover.**
Give each card `--card-z: 0|1|2`, and drive shadow strength, border alpha, and surface lightness
from it. The featured card ships at `2`. This is what actually makes a row of cards read as
*layered* rather than *drawn*; tilt without it just wobbles flat rectangles.

**T0-2 · Pointer spotlight — highest yield per byte.**
One `pointermove` listener on the **grid container** (not four listeners), rAF-throttled, writing
`--mx`/`--my` as percentages. Each card's `::before` paints
`radial-gradient(240px circle at var(--mx) var(--my), var(--accent-dim), transparent 60%)`.
Because the coordinates are container-relative, the highlight sweeps *across* the four cards as one
continuous light source — which is the effect that sells depth. ~25 lines of JS.
Gate behind `@media (hover: hover) and (pointer: fine)` and `usePrefersReducedMotion()`.

**T0-3 · Travelling hairline via `@property`.**

```css
@property --beam { syntax: '<angle>'; initial-value: 0deg; inherits: false; }

.card-beam::after {
  content: '';
  position: absolute; inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: conic-gradient(from var(--beam), transparent 0 82%, var(--accent) 92%, transparent 100%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask-composite: exclude;
  animation: beam 6s linear infinite;
}
@keyframes beam { to { --beam: 360deg; } }
```

`@property` typing is what makes the angle interpolable at all. Animation of registered properties
is **Chromium-first**; elsewhere the gradient renders static, which is a perfectly good border.
Covered by the global reduced-motion `!important` block for free.

**T0-4 · The numeral as a depth plane.**
`01`–`04` are currently `--text-xs` mono labels. Promote a *ghost* copy to display size at ~6%
`--text`, positioned behind the heading and pushed back with `translateZ(-40px)` under the shared
perspective. Costs one element, no JS, and gives the card a literal foreground/background.

**T0-5 · Scroll-driven CSS (`animation-timeline: view()`) — verdict: no.**
It is genuinely the right primitive for reveals, but as of mid-2026 it is **not Baseline** —
Firefox stable still has it behind a flag ([MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/animation-timeline)),
support ~84%. The existing `useSectionReveal` IntersectionObserver already works everywhere and
already handles the `<noscript>` case. Adding a second reveal mechanism buys nothing and doubles
the surface where a card can end up stuck at `opacity: 0`.

### T1 — real CSS 3D

**T1-1 · One shared vanishing point.**
`perspective: 1200px` on the **grid**, `transform-style: preserve-3d` on the cards. Without a shared
perspective each card tilts in its own coordinate space and the row reads as four unrelated toys
rather than one physical surface. This is the single decision that separates "3D section" from
"cards with a tilt script".

**T1-2 · Pointer tilt, small.**
`rotateX/rotateY` derived from cursor position, lerped in rAF. Constraints learned from the ecosystem
consensus and from this codebase:
- **≤6° maximum.** Larger angles resample the text and the serif stems go soft.
- **Merge with `.card-hover`.** That utility already owns `transform`. A second `transform`
  declaration replaces it — the `-3px` lift silently disappears. One chain:
  `translateY(var(--lift)) rotateX(...) rotateY(...)`.
- **Containing-block trap.** A `transform` on the card makes it the containing block for any
  `position: fixed` descendant (UI plan §0). Nothing fixed lives there today.
- Gate on `(hover: hover) and (pointer: fine)` — tilt is meaningless on touch and the listener is
  pure cost there.
- **The flattening trap — the one that actually bit.** `overflow` (any value but `visible`),
  `clip-path`, `filter`, `opacity` below 1, and `mask` are *grouping properties*: each one forces
  `transform-style: preserve-3d` to compute to `flat`, with no warning and no error. A card that
  carries `overflow: hidden` to clip its decoration silently loses every `translateZ` inside it —
  the depth is simply not rendered. Clip in a **child wrapper** instead, and give that wrapper its
  own local `perspective` if its contents still need to read as 3D.

**T1-3 · Depth stacks that mean something.** See §4.

### T2 — WebGL / react-three-fiber — verdict: no

Tree-shaken three.js is ~150–200 KB, plus ~50 KB for the R3F reconciler; the untree-shaken bundles
are 462 KB / 1,036 KB. For a below-the-fold trust section on a page where organic search matters,
that is a Core Web Vitals cost with no corresponding capability gain — CSS 3D covers every effect
described here. The 2026 consensus for marketing pages is the same: CSS 3D and a small JS layer
deliver more per hour than a WebGL runtime.

If a canvas is ever genuinely wanted, hand-roll a 2D-context line/particle field (~3 KB) rather than
importing a scene graph.

### T3 — the existing gooey layer — reuse the idea, not the filter

`#goo` is global and already instantiated. But the UI plan §C.5 caps it at **one gooey layer per
viewport**, and the hero owns it; two overlapping full-bleed `filter: url(#goo)` layers is a
dropped-frame generator on integrated graphics. For the features band, plain blurred radial
gradients at 8–16% `--accent` get ~90% of the look at approximately zero cost, and — importantly —
do not create another `filter` containing block.

---

## 4. The recommended composition

The strongest available move is **not** to apply one effect to four cards. It is to let each card's
FX *be* its content. Same tech budget, four times the meaning, and it stops the section reading as a
component demo.

| # | Card | FX that means the content | Tier |
|---|---|---|---|
| 01 | Verified Reasoning | Three epistemic chips — VERIFIED / HYPOTHESIS / UNKNOWN — resolving on reveal. Reuses the existing `.epistemic-verified/-hypothesis/-unknown` utilities (`globals.css:981-992`), so the decoration is the product's own vocabulary. Card sits at `--card-z: 2`, the only filled surface. | T0 |
| 02 | Cross-Lab Consensus | Three ghost planes behind the card at increasing `translateZ`, offset and rotated a few degrees — a literal stack of parallel agents. They converge toward the card plane on hover. | T1 |
| 03 | Grounded Research | A citation thread: an SVG path from a claim line to a source marker, drawn with `stroke-dashoffset` on reveal. **Correction:** the source marker cannot be put on a plane behind the claim *inside* the SVG — SVG has no 3D coordinate system, so `translateZ` on an SVG child is dropped. Either accept recession-by-opacity, or make claim and source two HTML elements with the SVG as a flat connector between them. | T0 |
| 04 | Adversarial Critique | A counter-plane in `--red` sliding across at a slight `rotateY`, then being rejected — retreating and fading. The only card allowed the red token. | T1 |

Shared across all four: the grid perspective (T1-1), the container spotlight (T0-2), the elevation
token (T0-1), and the ghost numeral (T0-4).

**Bento geometry warning.** Card 01 and 04 span two columns; 02 and 03 do not. Per-card FX must not
change intrinsic height differently, or the 2+1+1+2 layout stops filling whole rows and the grid
ends ragged — the exact failure the comment block at `LandingPage.tsx:21-51` exists to prevent.
Keep every added element absolutely positioned or `aspect-ratio`-locked.

---

## 5. Gates — non-negotiable before ship

| Gate | Why | Check |
|---|---|---|
| `usePrefersReducedMotion()` on every JS-driven effect | The global `!important` block covers CSS only; a rAF loop ignores it entirely | Toggle OS reduced-motion; no listener attached, no transform written |
| `@media (hover: hover) and (pointer: fine)` on spotlight + tilt | Touch has no hover; the listener is pure battery cost and the effect can strand a card mid-tilt | Test on a real touch device, not devtools emulation |
| Contrast re-measured on the inverted ground | §2.3 — the light accent is 2.7:1 there | Every text/border token in the band, computed not eyeballed |
| `prefers-contrast: more` entry for the band | `globals.css:1024` does not cover a new scope | Force the media feature; borders must thicken |
| One `transform` chain per card | `.card-hover` already owns `transform` | Hover a card with tilt active; the `-3px` lift must still happen |
| Promoted-layer budget | 4 cards × 3 ghost planes + spotlight pseudo = 16+ composited layers | Chrome DevTools → Layers; watch for a memory spike on low-end |
| Reveal still works with JS off | `<noscript>` escape hatch exists and must keep covering the new markup | Disable JS; all four cards fully visible and readable |
| Not the LCP element | Band is below the fold; any image must not become LCP | Lighthouse, mobile throttling |

---

## 6. Generated imagery

### 6.1 What must not be generated

| Forbidden | Why |
|---|---|
| Photoreal people ("our researchers", "our users") | A fabricated person on a page arguing against fabrication. Also the single most-recognised AI-stock tell. |
| Fake dashboards, fake charts, fake model output, fake lab logos | Indistinguishable from a claim. Directly violates the trust plan's governing principle. |
| Glowing brains, neural meshes, circuit boards, humanoid robots, holographic HUDs | The generic AI-landing-page vocabulary. Reads as a template, which is the opposite of what this section is arguing. |
| Anything with rendered text | Generated text is unreliable and unlocalisable, and a garbled word inside a "verified" card is a bad joke. |

### 6.2 Four directions that do work

**D1 · Editorial print abstraction.** Riso-print grain, halftone, letterpress deboss, folded-paper
geometry. Matches the ivory + serif + hanging-punctuation language the site already speaks. Big
advantage: it renders as a **duotone**, so one asset can be re-tinted per theme with
`mask-image` + `background: var(--accent)` — one file, both themes, always on-palette.

**D2 · Frosted / liquid glass solids.** A still-life extension of `LiquidField`: chunky translucent
forms, subsurface scatter, warm coral refraction. Looks best on the inverted (dark) band, which is
exactly where this section is going. Hardest of the four to keep on-brand; needs the strongest model
and the most iterations.

**D3 · Wireframe / topographic line fields.** Pure stroke art. Exports to real SVG, strokes take
`currentColor` so it is **theme-agnostic by construction**, animates via `stroke-dashoffset`, and
weighs ~2 KB per figure. Best cost-to-quality ratio for this project by a wide margin.

**D4 · Data sculpture.** An abstract lattice whose structure *is* the pipeline — parallel nodes
converging through a critique gate to a single synthesis. Honest, because it is structurally true.
Risk: if it looks too much like a real diagram it becomes a claim; keep it clearly non-quantitative
(no axes, no labels, no numbers).

**Recommendation: D3 inside the cards, D1 or D2 as a single band-wide backdrop at low opacity.**
D3 alone will look more expensive than any generated raster, costs ~8 KB total, and can never be
off-brand or off-theme because it inherits the tokens.

### 6.3 Model shortlist (2026)

| Job | Model | Note |
|---|---|---|
| Vector / SVG line art, transparent output | **Recraft** | The only major generator with reliable native transparent-PNG **and** SVG export |
| Photoreal glass / material renders | **GPT Image 2**, **Nano Banana Pro**, **FLUX.2** | GPT Image 2 leads prompt adherence; Nano Banana Pro is the value pick |
| Art-directed abstraction, aesthetic control | **Midjourney V7** | Strongest look, weakest controllability |
| Editing an existing asset while keeping identity | **Nano Banana** (conversational), **Flux Kontext** | For producing the light/dark pair from one master |

**Alpha-channel reality:** FLUX, Nano Banana, GPT Image and Midjourney do **not** emit an alpha
channel — Midjourney's editor offers only a hard-edged cutout. If transparency is required, either
generate in Recraft or generate on a flat key colour and matte it afterwards. Plan for this before
art-directing something that needs to float on the band.

### 6.4 Consistency method

The 2026 consensus is three layers: documented brand DNA → a fixed prompt prefix → reference-image
conditioning. For this project the brand DNA is already written down and does not need inventing:

> Ivory `#FAF9F5` / ink `#131211`. Warm low-chroma neutrals, ~40° hue bias. Coral accent family
> (`#D97757` brand fill; `#96401F` light-safe, `#E39B80` dark-safe). Editorial serif. Matte, not
> glossy. Generous negative space.

**Prompt template** — geometry / material / mood, in that order:

```
[GEOMETRY]  four interlocking translucent planes at staggered depth; one plane foremost
            and sharply lit, three receding into soft focus
[MATERIAL]  frosted glass with warm coral (#D97757) subsurface scattering, matte ivory
            (#FAF9F5) ground plane, no chrome, no rainbow iridescence
[MOOD]      soft top-left key light, deep soft shadow, editorial studio photography,
            shallow depth of field, centred composition, generous negative space,
            plain flat background
[NEGATIVE]  no text, no logos, no people, no glowing brain, no circuit board, no robot,
            no neon, no cyberpunk, no lens flare, no HUD, no charts, no UI
```

Swap `[MATERIAL]` alone to re-skin the whole set — brushed clay, pressed paper, matte ceramic —
while `[GEOMETRY]` and `[MOOD]` hold the family together. Feed the first accepted render back as a
reference image for the remaining three; that is what keeps card 04 looking like card 01.

### 6.5 Delivery spec

| Item | Requirement |
|---|---|
| Format | AVIF + WebP via `<picture>`; SVG where the asset is line art (D3) |
| Density | 1× and 2× only; no 3× |
| Budget | ≤60 KB per card, ≤120 KB for the band backdrop |
| Attributes | explicit `width`/`height` (CLS), `loading="lazy"`, `decoding="async"` |
| Semantics | decorative: `alt=""` **and** `aria-hidden="true"` |
| Theming | prefer one tintable master via `mask-image` + `background: var(--accent)`. Ship a second file only if the asset genuinely cannot be masked |
| Placement | must not become LCP — the band is below the fold and must stay that way |

---

## 7. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| D-1 | Invert mechanism: A (token override), B (`light-dark()` scoped), C (container style queries) | **B**, scoped to this band's ~14 tokens. C is the right destination once Firefox ships style queries. |
| D-2 | Full-bleed hard edge vs inset slab | **Hard full-bleed**, and delete the two `<Rule />` separators around this section. |
| D-3 | Uniform FX vs per-card semantic FX | **Per-card.** Same budget, four times the meaning. |
| D-4 | Imagery: generated raster vs SVG line art | **SVG line art (D3)** in-card; generated raster only as a single low-opacity band backdrop, if at all. |
| D-5 | Does the header's glass tint get fixed for the dark band? | Investigate before ship; not a blocker. |

---

## Sources

- [Inverted themes with `light-dark()` — Dave Rupert](https://daverupert.com/2026/04/inverted-light-dark/)
- ["Dark Mode" vs "Inverted" — Brad Frost](https://bradfrost.com/blog/post/dark-mode-vs-inverted/)
- [`light-dark()` — CSS-Tricks Almanac](https://css-tricks.com/almanac/functions/l/light-dark/)
- [`animation-timeline` — MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/animation-timeline)
- [CSS Scroll-Driven Animations guide (2026) — CSSAWWWARDS](https://cssawwwards.com/blog/css-scroll-driven-animations-guide-2026)
- [CSS `@property` and the New Style — Ryan Mulligan](https://ryanmulligan.dev/blog/css-property-new-style/)
- [Animated gradient borders with conic gradients — DoCode](https://docode.co.in/post/animated-border-card-with-conic-gradient-using-pure-css)
- [CSS card hover effects, pure-CSS vs JS breakdown — CodeFronts](https://codefronts.com/motion/css-card-hover-effects/)
- [High-performance CSS 3D transforms, no WebGL — DEV](https://dev.to/csslive/elevate-your-web-ui-high-performance-css-3d-transforms-no-webgl-required-4e93)
- [three.js vs React Three Fiber vs Babylon.js, bundle sizes — PkgPulse](https://www.pkgpulse.com/guides/threejs-vs-react-three-fiber-vs-babylonjs-3d-webgl-2026)
- [WebGL & three.js site SEO — Utsubo](https://www.utsubo.com/blog/webgl-three-js-site-seo-rankable-guide)
- [Which AI image generators support transparent PNGs (2026) — Transparify](https://transparify.app/blog/ai-image-generators-transparent-background)
- [AI image model comparison, April 2026 — JQ AI Systems](https://www.ai.joaoqueiros.com/blog/ai-image-model-comparison-2026)
- [Best AI image generators 2026 — BuildMVPFast](https://www.buildmvpfast.com/articles/best-llms-2026-guide/image-generation-ai)
- [Consistent brand style with AI — getimg.ai](https://getimg.ai/blog/how-to-generate-images-in-consistent-brand-style-with-ai)
- [Abstract 3D prompt structure — Hyper3D](https://hyper3d.ai/styles/abstract)
- [Using AI for 3D rendering, a practical guide — UX Collective](https://uxdesign.cc/using-ai-for-3d-rendering-a-practical-guide-for-designers-a2a037ed1ad0)
