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
  design; on a phone the live fragment comes before the button; the critic's input
  excerpts are quoted material in secondary ink.
- Next: roll `.site` and the components to the marketing pages (/how-it-works,
  /capabilities, /developers, /security, /privacy, /pricing, /contact, /for/[sector], /about),
  replacing `SiteHeader` / `SiteFooter` there. Then the app screens as their own run.
- Sample content to confirm: the pilot example problems in `PilotPinned.tsx` and
  `PilotDialog.tsx` are illustrations, not client work.
