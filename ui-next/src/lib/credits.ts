/**
 * Credit figures as the backend defines them, for the pricing, signup, FAQ
 * and about pages, the credit calculator and the dashboard.
 *
 * CREDITS_PER_USD and the monthly allowances mirror
 * src/reasoner/domain/credits.py (CREDITS_PER_USD, TIER_MONTHLY_CREDITS),
 * served publicly at GET /api/credits/pricing. The per-run costs are the
 * typical ranges in the "credits" docs page (lib/docs.ts): approximate,
 * since a run is charged afterwards from what its models actually cost.
 */
export const CREDITS_PER_USD = 1000;

export const TIER_CREDITS = [
  { tier: 'free', name: 'Free', credits: 500 },
  { tier: 'pro', name: 'Pro', credits: 25_000 },
  { tier: 'enterprise', name: 'Enterprise', credits: 250_000 },
] as const;

export type Tier = (typeof TIER_CREDITS)[number]['tier'];

/** The free plan's monthly allowance. The annotation fails the type check if
 *  the first tier stops being 'free', instead of a lookup quietly yielding 0. */
const FREE_TIER: { tier: 'free'; credits: number } = TIER_CREDITS[0];
export const FREE_CREDITS = FREE_TIER.credits;

/** Typical cost of one run, in credits: [low, high]. */
export const RUN_COSTS = [
  { kind: 'Direct answer', cost: [0, 2] },
  { kind: 'Web search answer', cost: [2, 8] },
  { kind: 'Budget pipeline', cost: [20, 20] },
  { kind: 'Premium pipeline', cost: [150, 300] },
] as const;

/** Runs a monthly allowance covers at a cost range, as display text. */
export function runsPerMonth(credits: number, [low, high]: readonly [number, number]): string {
  const fmt = (n: number) => Math.floor(n).toLocaleString('en-US');
  if (low === 0) return `${fmt(credits / high)} or more`;
  if (low === high) return `about ${fmt(credits / low)}`;
  return `${fmt(credits / high)}–${fmt(credits / low)}`;
}
