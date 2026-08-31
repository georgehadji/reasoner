'use client';

import { useId, useState } from 'react';
import { RUN, RUN_MODELS, type Block } from '@/lib/demo-record';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { Marks } from './Segments';

/**
 * The product's argument, made structurally rather than stated.
 *
 * One paragraph of real output, rendered twice from the same parsed blocks.
 * "Answer only" drops every apparatus segment — citations, epistemic labels —
 * and empties the margin rail. "Answer + record" puts them back. The reflow
 * between the two IS the explanation: you watch the provenance insert itself
 * into the sentences, and you watch the rail fill with figures that were
 * always there and simply were not shown.
 *
 * Every figure in the rail is counted from the run, never typed in.
 */

function SynthesisBlocks({ blocks, withRecord }: { blocks: Block[]; withRecord: boolean }) {
  return (
    <div className="prose-measure text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-2)]">
      {blocks.map((block, i) => {
        switch (block.kind) {
          case 'heading':
            return (
              <h3
                key={i}
                className="mt-[var(--space-8)] font-sans text-[length:var(--text-xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)] first:mt-0"
              >
                {block.text}
              </h3>
            );
          case 'subheading':
            return (
              <h4
                key={i}
                className="mt-[var(--space-6)] font-serif text-[length:var(--text-base)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]"
              >
                {block.text}
              </h4>
            );
          case 'item':
            return (
              <p key={i} className="mt-[var(--space-3)] flex gap-[var(--space-3)]">
                <span
                  aria-hidden="true"
                  className="nums-tabular shrink-0 font-mono text-[length:var(--text-xs)] text-[var(--text-subtle)]"
                >
                  {block.ordinal ? `${block.ordinal}.` : '—'}
                </span>
                <span>
                  <Marks segments={block.segments} withRecord={withRecord} />
                </span>
              </p>
            );
          case 'para':
            return (
              <p key={i} className="mt-[var(--space-4)]">
                <Marks segments={block.segments} withRecord={withRecord} />
              </p>
            );
        }
      })}
    </div>
  );
}

/* Counted, never typed. If the captured run is replaced these move with it. */
const RETAINED = RUN.scores.filter((s) => s.retained).length;
const PRUNED = RUN.scores.length - RETAINED;
const BIAS_FLAGS = RUN.scores.reduce((n, s) => n + s.biasFlags.length, 0);
const LABEL_COUNT = RUN.synthesis.reduce(
  (n, b) => n + (b.kind === 'para' || b.kind === 'item'
    ? b.segments.filter((s) => s.kind === 'label').length
    : 0),
  0,
);

const RAIL: Array<{ term: string; value: string }> = [
  { term: 'Sources cited', value: `${RUN.citations.length}, each linked` },
  { term: 'Claims labelled', value: `${LABEL_COUNT} VERIFIED` },
  { term: 'Positions argued', value: `${RUN.scores.length} — ${RETAINED} kept, ${PRUNED} pruned` },
  { term: 'Bias flags raised', value: String(BIAS_FLAGS) },
  {
    term: 'Adversarial tests',
    value: RUN.stress.map((t) => `${Math.round(t.survivalRate * 100)}%`).join(' · ') + ' survival',
  },
  { term: 'Models involved', value: `${RUN_MODELS.length} across competing labs` },
  { term: 'Cost of the record', value: `$${RUN.ledger.costUsd.toFixed(4)}` },
];

export function ApparatusToggle() {
  const [withRecord, setWithRecord] = useState(true);
  const reduced = usePrefersReducedMotion();
  const groupId = useId();

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-[var(--space-4)] border-b border-[var(--border)] pb-[var(--space-4)]">
        <p
          id={groupId}
          className="font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]"
        >
          The same synthesis, with and without its record.
        </p>

        {/* Rounded — because on this page a rounded outline means "you can
            operate this". It is one of only two such shapes in the document. */}
        <div
          role="group"
          aria-labelledby={groupId}
          className="flex shrink-0 rounded-[var(--radius-pill)] border border-[var(--border)] p-[2px]"
        >
          {[
            { label: 'Answer only', on: false },
            { label: 'Answer + record', on: true },
          ].map(({ label, on }) => (
            <button
              key={label}
              type="button"
              aria-pressed={withRecord === on}
              onClick={() => setWithRecord(on)}
              className={`min-touch rounded-[var(--radius-pill)] px-[var(--space-4)] py-[var(--space-2)] font-sans text-[length:var(--text-sm)] font-medium leading-[var(--lh-ui)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] ${
                withRecord === on
                  ? 'bg-[var(--accent)] text-[var(--accent-text)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-[var(--space-8)] pt-[var(--space-8)] lg:grid-cols-[minmax(0,1fr)_16rem]">
        {/* Keyed on the mode so the switch re-runs the entrance keyframe: the
            apparatus visibly arrives rather than blinking into place. Reduced
            motion drops the key, so the text simply changes. */}
        <div
          key={reduced ? 'static' : String(withRecord)}
          className={reduced ? undefined : 'animate-fade-up'}
        >
          <SynthesisBlocks blocks={RUN.synthesis} withRecord={withRecord} />
        </div>

        <dl
          className="h-fit border-t border-[var(--border)] pt-[var(--space-4)] lg:border-l lg:border-t-0 lg:pl-[var(--space-6)] lg:pt-0"
          aria-live="polite"
        >
          {RAIL.map(({ term, value }) => (
            <div key={term} className="mb-[var(--space-4)]">
              <dt className="font-sans text-[length:var(--text-2xs)] uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                {term}
              </dt>
              <dd
                className={`nums-tabular mt-[var(--space-1)] font-mono text-[length:var(--text-xs)] leading-[var(--lh-ui)] transition-colors duration-[var(--dur-state)] ${
                  withRecord ? 'text-[var(--text-2)]' : 'text-[var(--text-subtle)]'
                }`}
              >
                {withRecord ? value : '—'}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
