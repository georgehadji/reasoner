/**
 * A real four-model image run, captured 2026-08-27 from the production code
 * path (`generate_images(preset="budget", num_images=4)`).
 *
 * Two of the four are the budget tier's configured primaries; the other two are
 * fallbacks that took over when Krea and Alibaba failed on the call. That is
 * left exactly as it happened rather than re-rolled for a tidier lineup — the
 * fallback chain doing its job is the more honest demonstration, and a page
 * that claims resilience should show it working rather than assert it.
 *
 * The prompt is chosen to make the labs disagree. A quiet interior is where
 * four models agree, which makes four plates under a heading about four
 * different labs read as a stock-photo grid; rain, night and a single light
 * source is where house style, colour grading and tone-mapping visibly part.
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
  'A street food stall at dusk in heavy rain, one bare hanging bulb above the counter, steam rising off the griddle, wet asphalt reflecting the light, no people, cinematic';

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
    model: 'grok-imagine',
    lab: 'xAI',
    origin: 'United States',
    fallback: true,
  },
  {
    src: '/showcase/image-4.webp',
    model: 'gpt-5-image-mini',
    lab: 'OpenAI',
    origin: 'United States',
    fallback: true,
  },
] as const;
