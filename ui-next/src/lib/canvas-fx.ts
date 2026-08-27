/**
 * Deterministic RNG and CSS-token colour decoding shared by the landing
 * page's canvas effects (DisagreementField, IdeaField). Both need paint
 * output that agrees between the server-rendered markup and the first
 * client frame, and both need to read theme colour out of the cascade
 * rather than hardcoding it — extracted here once a second canvas needed
 * byte-identical copies of both.
 */

/**
 * Deterministic, so SSR markup and the first client frame cannot disagree,
 * and so a reduced-motion render (one frame, then nothing) is reproducible.
 */
export function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A CSS custom property resolves to hex; canvas fillStyle needs the channels. */
export function readChannels(root: HTMLElement, token: string, fallback: string): string {
  const raw = getComputedStyle(root).getPropertyValue(token).trim() || fallback;
  const hex = raw.startsWith('#') ? raw.slice(1) : raw;

  if (hex.length !== 6) return '128,128,128';

  const value = Number.parseInt(hex, 16);
  if (Number.isNaN(value)) return '128,128,128';

  return `${(value >> 16) & 255},${(value >> 8) & 255},${value & 255}`;
}
