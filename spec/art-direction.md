# Art Direction — Reasoner · OVERPRINT

**Status:** adopted 2026-11-13, replacing the "Apparatus" direction (warm-tan ground,
hueless accent, Piazzolla + Public Sans). The old document is in git history at
`f4d282d6:spec/art-direction.md`. Its measurements of the run data (§0 there) still
hold and still matter: epistemic labels are dense in Phase 2 and sparse in synthesis.

Tokens: `ui-next/src/styles/tokens.css`. Gate: `node scripts/check-contrast.mjs`.

---

## 1. The idea

The site is **printed, not painted**: a two-drum risograph pass on newsprint.

- **Federal blue** (`--ink-blue`, `#1F3FBF`) is the working ink. It carries every
  link and primary control.
- **Fluorescent pink** (`--ink-pink`, `#FF4F9A`) is the second drum. It is a fill
  only: plates, registration offsets, the signature.
- Where they overlap they make **violet** (`--ink-overlap`, `#6438A0`).

Why print: the product's claim is that answers come from models of different labs
that are run separately and never merged. A riso pass is literally that: separate
drums, run separately, that never land exactly on top of each other. The
misregistration is not decoration; it is the product's shape.

## 2. Signature — the plates never register

Each Phase 2 perspective (`components/phases/PerspectivesRenderer.tsx`) and each lab
plate on the landing image exhibit is printed on its own pink plate (`.misregister`
in `globals.css`). Each item in a run of four gets a different offset, in a
different direction. On load the plates settle once, from 3x offset to 1x, under
`--dur-scene`. They never reach zero. Under `prefers-reduced-motion` they render at
rest.

This is the one orchestrated moment per page the banlist allows.

## 3. Global print layer

Applied in `globals.css`, so every route picks it up with no call-site change:

| Move | Rule |
|---|---|
| Grain | `body::after`, fixed SVG noise, `--grain-opacity` (0.07 / 0.06), multiplied on newsprint, screened on carbon. `pointer-events: none`, hidden in print. |
| Overprinted headings | `h1.font-display`, `h2.font-display`, `.overprint`: ink with the pink drum offset `0.05em 0.035em` under it. |
| Expanded display | `.font-display` runs Archivo's `wdth` axis: 100% below 48rem, 112% to 80rem, 125% above. `hyphens: auto` so a long word never breaks mid-letter or pushes the page sideways. |
| Plate corners | Radius 2 / 3 / 4 / 6px. Trimmed sheet, not app card. Not zero (banlist item 4). Pills stay round. |
| Floating layers | `--shadow-float` is a hard 4px ink offset, not a blur. Print has no soft shadows. |

## 4. Type

All OFL, all via `next/font/google` (see `ui-next/src/app/fonts.ts`).

| Role | Face | Utility |
|---|---|---|
| Display | **Archivo**, variable `wght` + `wdth` | `font-display` |
| Body + UI | **Atkinson Hyperlegible Next**, variable `wght` | `font-sans` (default) |
| Code, model IDs, tables | **Inconsolata** (unchanged, not preloaded) | `font-mono` |

Atkinson was drawn so that `I l 1` and `O 0` never collide. A reader checking model
IDs and figures is who that serves. Archivo expanded is wide poster type that
survives a two-ink print.

`font-serif` is gone. The old utility was renamed to `font-display` at every call site.
The `.prose-serif` class name survives and already sets sans.

## 5. Colour

Light is the base (newsprint, `#F1F3F0`, cool on purpose: the banlist forbids
cream + serif + clay). Dark is carbon stock (`#121318`) with both drums lifted.

**Hue is no longer reserved for data.** That reverses the previous commitment, and
PRODUCT.md is updated to match. The epistemic labels lean on their carrier first
(`.epistemic-*`: solid / dashed / dotted left rule) and their ink second:

| Label | Light | Dark | Why this ink |
|---|---|---|---|
| VERIFIED | teal `#00656A` | `#4FC7C2` | riso teal, clear of both drums |
| HYPOTHESIS | violet `#6438A0` | `#B79AF0` | the overlap ink: two drums, not settled |
| UNKNOWN | ochre `#735400` | `#D9B24A` | riso yellow, darkened to read |
| Danger | `#B3122E` | `#FF7A7A` | `--red`, unchanged role |

Rules:
- `--ink-pink` is **never text on newsprint** (2.75:1). Use `--ink-pink-text`
  (`#B8155C`, AA everywhere). Ink on a pink fill uses `--text` (6.04:1).
- All text inks clear AA on all nine grounds in both themes; `--text-subtle` no
  longer carries a ground restriction. `check-contrast.mjs`: 164 pairs pass.
- Values ship as hex: `lib/canvas-fx.ts` paints mid-grey for anything else.
- The dark palette exists in five places (two in `tokens.css`, three
  `.invert-band` blocks in `globals.css`). Edit all five.

## 6. Removed

- The two radial "light" gradients behind the landing image grid and
  `ReviewHandoff`. Soft glows belong to the painted world, and both bled 8% past the
  viewport, which caused sideways scroll at 1024px.

## 7. Open

- **Taste check by a human.** Look at `/` and `/chat` for ten seconds in both themes.
  The two levers if it is too loud: `--grain-opacity`, and the heading offset in
  `h1.font-display` (`0.05em 0.035em`).
- **HYPOTHESIS violet equals `--ink-overlap`.** Deliberate, as described above, but a
  HYPOTHESIS mark next to a violet overlap area could be misread. The dashed carrier
  is what separates them.
- **Not yet reworked for print:** composition of `/pricing`, `/settings`,
  `/dashboard` and the chat shell. They take the new tokens, type and corners, but
  their layouts are the previous ones.
