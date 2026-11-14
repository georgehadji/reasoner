'use client';

import { useState } from 'react';
import { Marks } from '@/components/run-record/Segments';
import { RUN, SCORE_AXES } from '@/lib/demo-record';

/**
 * Input half, output half. Left, on the dark field: the four positions the
 * run's generators wrote, blind to each other, as the critic received them.
 * Right, on the light field: the critic's score sheet for the same four.
 * Pointing at a row on either side marks its pair on the other.
 *
 * All values from the captured run (lib/demo-record.ts).
 */
const ROLE: Record<string, string> = {
  constructive: 'Constructive',
  destructive: 'Destructive',
  systemic: 'Systemic',
  minimalist: 'Minimalist',
};

const AXIS_SHORT: Record<string, string> = {
  logicalConsistency: 'Logic',
  evidenceSupport: 'Evidence',
  failureResilience: 'Resilience',
  feasibility: 'Feasibility',
};

export function CritiqueSplit() {
  const [active, setActive] = useState<string | null>(null);
  const kept = RUN.scores.filter((s) => s.retained).length;

  return (
    <section id="critique" aria-labelledby="critique-a" className="grid lg:grid-cols-2">
      {/* Dark field: what the critic is handed. */}
      <div className="flex min-h-[var(--site-stack-h)] flex-col justify-between gap-[var(--space-12)] bg-[var(--site-bg)] px-[var(--site-margin)] py-[var(--space-16)] lg:min-h-[var(--site-field-h)]">
        <ol className="max-w-[34ch] space-y-[var(--space-6)] lg:mt-[12svh]" data-reveal>
          {RUN.positions.map((p) => (
            <li
              key={p.id}
              onPointerEnter={() => setActive(p.id)}
              onPointerLeave={() => setActive(null)}
              className={`border-l-2 pl-[var(--space-4)] transition-colors duration-[var(--dur-state)] ${
                active === p.id ? 'border-[var(--site-accent)]' : 'border-transparent'
              }`}
            >
              <p className="font-semibold text-[length:var(--site-body)]">{ROLE[p.id] ?? p.id}</p>
              <p className="mt-[var(--space-1)] line-clamp-3 text-[length:var(--site-body)] leading-[var(--site-lh-body)] text-[var(--site-muted)]">
                <Marks segments={p.excerpt} withRecord={false} />
              </p>
            </li>
          ))}
        </ol>
        <h2 id="critique-a" aria-label="Four answers, one critic." className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
          Four answers,
        </h2>
      </div>

      {/* Light field: what the critic hands back. */}
      <div className="flex min-h-[var(--site-stack-h)] flex-col justify-between gap-[var(--space-12)] bg-[var(--site-field)] px-[var(--site-margin)] py-[var(--space-16)] text-[var(--site-field-ink)] lg:min-h-[var(--site-field-h)]">
        <div data-ui data-reveal className="w-full min-w-0 max-w-[var(--site-fragment)] overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] text-[var(--site-ink)] lg:mt-[12svh]">
          <table className="w-full border-collapse nums-tabular">
            <caption className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-left font-semibold">
              Critique and pruning · {kept} of {RUN.scores.length} kept
            </caption>
            <thead className="text-[var(--site-muted)]">
              <tr>
                <th scope="col" className="px-[var(--space-4)] py-[var(--space-2)] text-left font-normal">Position</th>
                {SCORE_AXES.map((a) => (
                  <th key={a.key} scope="col" title={a.label} className="hidden px-[var(--space-2)] py-[var(--space-2)] text-right font-normal sm:table-cell">
                    {AXIS_SHORT[a.key]}
                  </th>
                ))}
                <th scope="col" className="px-[var(--space-4)] py-[var(--space-2)] text-right font-normal">Total</th>
              </tr>
            </thead>
            <tbody>
              {RUN.scores.map((s) => (
                <tr
                  key={s.position}
                  onPointerEnter={() => setActive(s.position)}
                  onPointerLeave={() => setActive(null)}
                  className={`border-t border-[var(--site-line)] transition-colors duration-[var(--dur-state)] ${
                    active === s.position ? 'bg-[var(--site-surface-2)]' : ''
                  }`}
                >
                  <th scope="row" className="px-[var(--space-4)] py-[var(--space-2)] text-left font-semibold">
                    {ROLE[s.position] ?? s.position}
                    <span className="block font-normal text-[var(--site-muted)]">{s.retained ? 'Kept' : 'Pruned'}</span>
                  </th>
                  {SCORE_AXES.map((a) => (
                    <td key={a.key} className="hidden px-[var(--space-2)] py-[var(--space-2)] text-right sm:table-cell">
                      {s[a.key]}
                    </td>
                  ))}
                  <td className={`px-[var(--space-4)] py-[var(--space-2)] text-right font-semibold ${s.retained ? 'text-[var(--site-accent)]' : ''}`}>
                    {s.total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="lg:text-right">
          <p aria-hidden="true" className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
            one critic.
          </p>
          <p className="mt-[var(--space-4)] max-w-[44ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)] text-[var(--site-field-muted)] lg:ml-auto">
            A model from outside the dominant lab scores every position on four axes. Pruned
            positions stay on the record in their strongest form.
          </p>
        </div>
      </div>
    </section>
  );
}
