/**
 * Typography — three variable families, self-hosted by next/font.
 *
 * Roles: display (Archivo, set expanded) carries headings only; sans
 * (Atkinson Hyperlegible Next) carries body copy and UI chrome; mono
 * carries code, model IDs and token values. See spec/art-direction.md.
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
import { Archivo, Atkinson_Hyperlegible_Next, Inconsolata } from 'next/font/google';

/** Body copy and UI chrome. Drawn by the Braille Institute so that
 *  similar letterforms (I l 1, O 0) never collide — a reader checking
 *  model IDs and figures is exactly who that serves. */
export const atkinson = Atkinson_Hyperlegible_Next({
  subsets: ['latin'],
  variable: '--font-atkinson',
  display: 'swap',
  preload: true,
});

/** Display only. Archivo is loaded with its `wdth` axis so headings can
 *  run expanded (`font-stretch` on .font-display in globals.css) — wide,
 *  heavy poster type that survives a two-ink print. */
export const archivo = Archivo({
  subsets: ['latin'],
  variable: '--font-archivo',
  axes: ['wdth'],
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
  atkinson.variable,
  archivo.variable,
  inconsolata.variable,
].join(' ');
