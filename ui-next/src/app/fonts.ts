/**
 * Typography — three variable families, self-hosted by next/font.
 *
 * Roles are deliberately split. Sans carries UI chrome (nav, buttons,
 * labels, data); serif carries running prose (synthesis output, docs,
 * marketing copy); mono carries code, model IDs, and token values.
 *
 * All three are subset to `latin` and loaded with `display: 'swap'`.
 * next/font self-hosts and emits a size-adjusted fallback automatically,
 * so there is no external request and no layout shift on first paint.
 * That generated fallback is why no manual `@font-face` belongs here.
 *
 * `preload` is set per family by where the family first paints. Sans and
 * serif are above the fold on every route, so they get a `<link rel=
 * preload>`. Mono only appears in code blocks and token tables further
 * down the page, so preloading it would contend with the two families
 * that actually block first meaningful paint.
 */
import { Instrument_Sans, Source_Serif_4, JetBrains_Mono } from 'next/font/google';

/** UI chrome. Tighter than Inter by default, which is what keeps a dense
 *  reasoning UI compact at 11–13px. Above the fold everywhere. */
export const instrumentSans = Instrument_Sans({
  subsets: ['latin'],
  variable: '--font-instrument-sans',
  display: 'swap',
  preload: true,
});

/** Running prose. The `opsz` axis lets one family cover 15px paragraphs
 *  and 60px headings without a second download. Above the fold everywhere. */
export const sourceSerif = Source_Serif_4({
  subsets: ['latin'],
  variable: '--font-source-serif',
  display: 'swap',
  preload: true,
});

/** Code, model IDs, token values, and anything tabular. Below the fold —
 *  deliberately not preloaded so it does not compete with sans/serif for
 *  the first connections. */
export const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
  preload: false,
});

/** Space-joined className carrying the three webfont CSS variables. */
export const fontVariables = [
  instrumentSans.variable,
  sourceSerif.variable,
  jetbrainsMono.variable,
].join(' ');

/*
 * Inter used to be loaded purely to fill the second slot of the `--font-sans`
 * chain. That slot was unreachable: next/font emits
 * `--font-instrument-sans: 'Instrument Sans', 'Instrument Sans Fallback'`, and
 * the size-adjusted local fallback already covers both the swap window and a
 * failed download. The payload never rendered a pixel, so both the import and
 * the `var(--font-inter)` reference in globals.css are gone.
 */
