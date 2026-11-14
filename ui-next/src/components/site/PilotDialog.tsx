'use client';

import { useRouter } from 'next/navigation';
import { useId, useState } from 'react';
import { PILOT_DRAFT_KEY } from '@/lib/pilot-draft';

/**
 * First step, already open: the pilot request as the product's own dialog.
 * The text and routing choice are carried to /contact in sessionStorage
 * (never the URL) and prefilled there; nothing is sent from this page.
 */
const EXAMPLE = 'Red-team our plan to move incident triage to a new vendor before the board meets.';

export function PilotDialog() {
  const router = useRouter();
  const [problem, setProblem] = useState(EXAMPLE);
  const [routing, setRouting] = useState<'All labs' | 'Western-only'>('All labs');
  const fieldId = useId();
  const titleId = useId();

  return (
    <section
      id="start"
      aria-labelledby="start-h"
      className="grid min-h-[var(--site-field-h)] gap-[var(--space-12)] bg-[var(--site-accent)] px-[var(--site-margin)] py-[var(--space-16)] text-[var(--site-accent-ink)] lg:grid-cols-12 lg:items-center"
    >
      <div className="lg:col-span-5 lg:self-end">
        <h2 id="start-h" className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
          <span className="block">Bring one</span>
          <span className="block">problem.</span>
        </h2>
        <p className="mt-[var(--space-6)] max-w-[44ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
          The button opens a short form with your problem filled in. A pilot is paid, runs four to
          six weeks, and is judged against your own team&rsquo;s analysis.
        </p>
      </div>

      <form
        data-ui
        role="dialog"
        aria-labelledby={titleId}
        onSubmit={(e) => {
          e.preventDefault();
          const draft = `${problem.trim()}\n\nRouting: ${routing}`;
          try {
            sessionStorage.setItem(PILOT_DRAFT_KEY, draft);
          } catch {
            /* storage blocked: the form opens empty */
          }
          router.push('/contact?topic=pilot');
        }}
        className="w-full max-w-[var(--site-dialog)] rounded-[var(--radius-lg)] bg-[var(--site-bg)] text-[var(--site-ink)] shadow-[var(--shadow)] lg:col-span-5 lg:col-start-7"
      >
        <p id={titleId} className="border-b border-[var(--site-line)] px-[var(--space-5)] py-[var(--space-4)] font-semibold">
          Propose a pilot
        </p>
        <div className="space-y-[var(--space-5)] p-[var(--space-5)]">
          <div>
            <label htmlFor={fieldId} className="text-[var(--site-muted)]">
              The problem
            </label>
            <textarea
              id={fieldId}
              rows={3}
              value={problem}
              onChange={(e) => setProblem(e.target.value)}
              className="mt-[var(--space-1)] w-full resize-none rounded-[var(--radius)] border border-[var(--site-line)] bg-[var(--site-surface)] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--site-body)] leading-[var(--site-lh-body)] focus:border-[var(--site-accent)]"
            />
          </div>
          <fieldset>
            <legend className="text-[var(--site-muted)]">Routing</legend>
            <div className="mt-[var(--space-1)] grid grid-cols-2 rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]">
              {(['All labs', 'Western-only'] as const).map((r) => (
                <label
                  key={r}
                  className={`cursor-pointer rounded-[var(--radius-sm)] px-[var(--space-3)] py-[var(--space-2)] text-center transition-colors duration-[var(--dur-micro)] has-[:focus-visible]:outline has-[:focus-visible]:outline-2 ${
                    routing === r ? 'bg-[var(--site-accent)] font-semibold text-[var(--site-accent-ink)]' : 'hover:bg-[var(--site-surface)]'
                  }`}
                >
                  <input type="radio" name="routing" value={r} checked={routing === r} onChange={() => setRouting(r)} className="sr-only" />
                  {r}
                </label>
              ))}
            </div>
          </fieldset>
          <button type="submit" className="site-button w-full">
            Continue to the form
          </button>
        </div>
      </form>
    </section>
  );
}
