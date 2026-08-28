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
import { Public_Sans, Piazzolla, Inconsolata } from 'next/font/google';

/** UI chrome. Public Sans (USWDS) — a Libre Franklin derivative drawn for
 *  documents that must be read by anyone and defended in public. Neutral
 *  without being Helvetica-neutral. Above the fold everywhere.
 *  Replaces DM Sans — see spec/art-direction.md §4, migration step 2a. */
export const publicSans = Public_Sans({
  subsets: ['latin'],
  variable: '--font-public-sans',
  display: 'swap',
  preload: true,
});

/** Display only (see globals.css --font-serif usage note). Piazzolla — a
 *  screen-first Palatino descendant with angular humanist forms; reads as
 *  a technical monograph rather than a magazine. Variable on both `wght`
 *  and `opsz`, so large display sizes get the optical-size cut for free.
 *  Replaces Newsreader — see spec/art-direction.md §4, migration step 2a. */
export const piazzolla = Piazzolla({
  subsets: ['latin'],
  variable: '--font-piazzolla',
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
  publicSans.variable,
  piazzolla.variable,
  inconsolata.variable,
].join(' ');
