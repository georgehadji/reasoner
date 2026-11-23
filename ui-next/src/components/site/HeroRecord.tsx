'use client';

import { useId, useState } from 'react';
import { CLAIM_SPECIMENS, RUN } from '@/lib/demo-record';
import { EPISTEMIC_TAG, epistemicClassName } from '@/lib/remark-epistemic';

/**
 * The hero's working fragment: three claims from one real run, with the
 * record switched on or off. Off, they read like any confident answer; on,
 * each carries the label the run gave it. That switch is the product's
 * whole argument, so it is the hero.
 *
 * The claims are lib/demo-record.ts's ranked specimens (one per label,
 * derived from a captured production run), never typed here.
 */
const SECONDS = Math.round(RUN.ledger.seconds);

export function HeroRecord() {
  const [withRecord, setWithRecord] = useState(true);
  const groupId = useId();

  return (
    <figure
      data-ui
      className="w-full max-w-[var(--site-fragment)] overflow-hidden rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] text-[var(--site-ink)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
        <span id={groupId} className="font-semibold">
          Claims from one run
        </span>
        <div role="group" aria-labelledby={groupId} className="flex rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]">
          {[
            { on: false, label: 'Answer only' },
            { on: true, label: 'With the record' },
          ].map(({ on, label }) => (
            <button
              key={label}
              type="button"
              aria-pressed={withRecord === on}
              onClick={() => setWithRecord(on)}
              className="rounded-[var(--radius-sm)] px-[var(--space-3)] py-[var(--space-1)] text-[var(--site-muted)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--site-ink)] aria-pressed:bg-[var(--site-accent)] aria-pressed:font-semibold aria-pressed:text-[var(--site-accent-ink)]"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-[var(--space-4)] pt-[var(--space-4)]">
        <p className="text-[var(--site-muted)]">Question</p>
        <p className="mt-[var(--space-1)] font-semibold">{RUN.question}</p>
      </div>

      <div key={String(withRecord)} className="space-y-[var(--space-3)] px-[var(--space-4)] py-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-body)] [animation:site-fade_var(--dur-component)_var(--ease-entrance)_both]">
        {CLAIM_SPECIMENS.map(({ claim, label, qualifier }) => (
          <p key={label}>
            {claim}
            {withRecord && (
              <span className={epistemicClassName(EPISTEMIC_TAG[label])}>
                {label}
                {qualifier ? ` ${qualifier}` : ''}
              </span>
            )}
          </p>
        ))}
      </div>

      <figcaption
        aria-live="polite"
        className="flex flex-wrap gap-x-[var(--space-4)] gap-y-[var(--space-1)] border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)] nums-tabular"
      >
        <span>{withRecord ? `${CLAIM_SPECIMENS.length} labels shown` : 'Labels hidden'}</span>
        <span>{RUN.phases.length} phases</span>
        <span>{SECONDS} s</span>
        <span>Captured {RUN.capturedOn}</span>
      </figcaption>
    </figure>
  );
}
