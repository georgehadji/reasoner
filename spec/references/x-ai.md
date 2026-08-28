# x.ai

Saved 2026-08-28. Values measured from computed styles.

## What is actually there
- Ground `#0A0A0A` true near-black; panel `#1F2228`; text white and `#E1E4E8`;
  warm grey `#D7D1C9`. Accents `#F97583` coral-pink and `#9ECBFF` pale blue — these are
  GitHub-dark syntax colours, so they arrive from code samples rather than from brand.
- Type: `universalSansDisplay` for headings, `universalSans` for body, and **GeistMono on
  253 elements** — mono is a first-class UI face here, not just code styling.
- Headings carry **hard negative tracking**: -1.5px at 60px, -1.2px at 48px, -0.75px at
  30px. Tracking scales with size rather than staying fixed.
- Hero headline animates per-character ("imagine." arrives letter by letter).
- Nav is a six-item mega-menu plus two CTAs — a much denser nav than the category norm.

## TAKE
- **Size-proportional negative tracking.** A real typographic system decision, costs
  nothing, and most AI sites do not do it. Directly portable to the type scale.
- Mono promoted to a UI face rather than quarantined into code blocks. Reasoner shows
  model IDs, token counts, phase names and costs — all of which are mono-native content.
- Warm grey `#D7D1C9` sitting inside an otherwise cold palette as the one soft note.

## DO NOT TAKE
- Per-character headline animation. Banlist: one orchestrated moment per page, and this
  is not the one worth spending it on.
- Syntax-highlight colours as brand accents — that is an accident, not a decision.
- Geist as a display face is banned outright. GeistMono as a *utility* face is not the
  same thing and is allowed, but choosing it is still choosing the default mono of 2025.

## Banlist status
PARTIAL on near-black ground. HIT on decorative motion. Retained for **tracking system
and mono-as-UI-face**.
