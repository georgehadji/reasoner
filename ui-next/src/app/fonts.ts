/**
 * Typography — three families, self-hosted by next/font.
 *
 * Roles (spec/art-direction.md §4): display (League Spartan 700) carries
 * headings only; sans (Figtree 400/600) carries body copy and UI chrome;
 * mono (Inconsolata) carries code, model IDs and token values, never
 * prose. The marketing type matches the product's interface type, so the
 * interface fragments on the site and the pages around them read as one
 * thing.
 *
 * All three are subset to `latin` and loaded with `display: 'swap'`.
 * next/font self-hosts and emits a size-adjusted fallback automatically,
 * so there is no external request and no layout shift on first paint.
 * That generated fallback is why no manual `@font-face` belongs here.
 *
 * `preload` is set per family by where the family first paints. Display
 * and body are above the fold on every route. Mono only appears in code
 * blocks and tables further down, so it is not preloaded.
 */
import { Figtree, Inconsolata, League_Spartan } from 'next/font/google';

/** Body copy and UI chrome: an open, friendly text sans. */
export const figtree = Figtree({
  subsets: ['latin'],
  weight: ['400', '600'],
  variable: '--font-figtree',
  display: 'swap',
  preload: true,
});

/** Display only, at one weight: a compact bold geometric with a low
 *  waist, set tight (-0.04em) in short sentence-case lines. */
export const leagueSpartan = League_Spartan({
  subsets: ['latin'],
  weight: ['700'],
  variable: '--font-spartan',
  display: 'swap',
  preload: true,
});

/** Code, model IDs, token values, and anything tabular. Below the fold —
 *  deliberately not preloaded. */
export const inconsolata = Inconsolata({
  subsets: ['latin'],
  variable: '--font-inconsolata',
  display: 'swap',
  preload: false,
});

/** Space-joined className carrying the three webfont CSS variables. */
export const fontVariables = [
  figtree.variable,
  leagueSpartan.variable,
  inconsolata.variable,
].join(' ');
