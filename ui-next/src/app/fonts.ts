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
import { DM_Sans, Newsreader, Inconsolata } from 'next/font/google';

/** UI chrome. DM Sans provides excellent UI clarity at dense sizing (11–13px).
 *  Above the fold everywhere. */
export const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-dm-sans',
  display: 'swap',
  preload: true,
});

/** Running prose. Newsreader is a contemporary serif optimized for screen reading.
 *  Above the fold everywhere. */
export const newsreader = Newsreader({
  subsets: ['latin'],
  variable: '--font-newsreader',
  display: 'swap',
  preload: true,
});

/** Code, model IDs, token values, and anything tabular. Inconsolata is a
 *  humanist monospace. Below the fold — deliberately not preloaded. */
export const inconsolata = Inconsolata({
  subsets: ['latin'],
  variable: '--font-inconsolata',
  display: 'swap',
  preload: false,
});

/** Space-joined className carrying the three webfont CSS variables. */
export const fontVariables = [
  dmSans.variable,
  newsreader.variable,
  inconsolata.variable,
].join(' ');
