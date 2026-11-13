'use client';

import { useState } from 'react';
import { RUN_COSTS, TIER_CREDITS, runsPerMonth, type Tier } from '@/lib/credits';

/**
 * /pricing's live fragment (data-ui): pick a plan, read how many runs of
 * each kind its monthly credits cover. Figures come from lib/credits.ts,
 * which mirrors the backend; per-run costs are the documented typical
 * ranges, so the counts are approximate and say so.
 */
export function CreditCalculator() {
  const [tier, setTier] = useState<Tier>('free');
  const plan = TIER_CREDITS.find((t) => t.tier === tier) ?? TIER_CREDITS[0];

  return (
    <figure
      data-ui
      className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
    >
      <div className="flex items-center justify-between gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
        <span className="font-semibold">How far a month goes</span>
        <span aria-live="polite" className="text-[var(--site-muted)] nums-tabular">
          {plan.credits.toLocaleString('en-US')} credits
        </span>
      </div>

      <div
        role="group"
        aria-label="Plan"
        className="m-[var(--space-3)] flex rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]"
      >
        {TIER_CREDITS.map((t) => (
          <button
            key={t.tier}
            type="button"
            aria-pressed={tier === t.tier}
            onClick={() => setTier(t.tier)}
            className="flex-1 rounded-[var(--radius-sm)] px-[var(--space-3)] py-[var(--space-1)] text-[var(--site-muted)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--site-ink)] aria-pressed:bg-[var(--site-accent)] aria-pressed:font-semibold aria-pressed:text-[var(--site-accent-ink)]"
          >
            {t.name}
          </button>
        ))}
      </div>

      <table className="w-full border-collapse nums-tabular">
        <thead className="text-[var(--site-muted)]">
          <tr>
            <th scope="col" className="px-[var(--space-4)] py-[var(--space-2)] text-left font-normal">
              Run
            </th>
            <th scope="col" className="px-[var(--space-2)] py-[var(--space-2)] text-right font-normal">
              Credits each
            </th>
            <th scope="col" className="px-[var(--space-4)] py-[var(--space-2)] text-right font-normal">
              Runs a month
            </th>
          </tr>
        </thead>
        <tbody>
          {RUN_COSTS.map(({ kind, cost: [low, high] }) => (
            <tr key={kind} className="border-t border-[var(--site-line)]">
              <th scope="row" className="px-[var(--space-4)] py-[var(--space-3)] text-left font-semibold">
                {kind}
              </th>
              <td className="px-[var(--space-2)] py-[var(--space-3)] text-right text-[var(--site-muted)]">
                {low === high ? `~${low}` : `${low}–${high}`}
              </td>
              <td className="px-[var(--space-4)] py-[var(--space-3)] text-right font-semibold text-[var(--site-accent)]">
                {runsPerMonth(plan.credits, [low, high])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <figcaption className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
        Typical costs. Each run is charged afterwards from what its models actually cost.
      </figcaption>
    </figure>
  );
}
