/**
 * A real four-model image run, captured 2026-08-18 from the production code
 * path (`generate_images(preset="budget", num_images=4)`).
 *
 * Two of the four are the budget tier's configured primaries; the other two are
 * fallbacks that took over when Krea and ByteDance failed on the call. That is
 * left exactly as it happened rather than re-rolled for a tidier lineup — the
 * fallback chain doing its job is the more honest demonstration, and a page
 * that claims resilience should show it working rather than assert it.
 *
 * Source of truth: `ui-next/public/showcase/manifest.json`.
 */

export interface ShowcaseImage {
  /** Path under /public. */
  src: string;
  /** The model that actually produced this image. */
  model: string;
  /** The lab behind that model. */
  lab: string;
  /** Where that lab is based — the page's cross-bloc claim is about this. */
  origin: string;
  /** True when this model was a fallback rather than a configured primary. */
  fallback?: boolean;
}

/** The prompt as typed, before automatic enhancement. */
export const SHOWCASE_PROMPT =
  'A single wooden reading chair beside a tall window in an empty gallery, early morning light raking across a bare floor, warm ivory walls, editorial photography, quiet and still';

export const SHOWCASE_IMAGES: readonly ShowcaseImage[] = [
  {
    src: '/showcase/image-1.webp',
    model: 'flux.2-klein-4b',
    lab: 'Black Forest Labs',
    origin: 'Germany',
  },
  {
    src: '/showcase/image-2.webp',
    model: 'riverflow-v2.5-fast',
    lab: 'Sourceful',
    origin: 'United States',
  },
  {
    src: '/showcase/image-3.webp',
    model: 'gemini-flash-image',
    lab: 'Google',
    origin: 'United States',
    fallback: true,
  },
  {
    src: '/showcase/image-4.webp',
    model: 'recraft-v4.1-utility',
    lab: 'Recraft',
    origin: 'United States',
    fallback: true,
  },
] as const;
