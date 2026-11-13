'use client';

import { useId, useState } from 'react';
import { RUN, RUN_MODELS, type Block, type EpistemicLabel } from '@/lib/demo-record';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { Marks } from './Segments';

/**
 * The product's argument, made structurally rather than stated (data-ui).
 *
 * One synthesis from the captured run, rendered twice from the same parsed
 * blocks. "Answer only" drops every apparatus segment (citations, epistemic
 * labels) and blanks the record beside it; "With the record" puts them back.
 * The reflow between the two is the explanation.
 *
 * Every figure beside the answer is counted from the run, never typed in.
 */

function SynthesisBlocks({ blocks, withRecord }: { blocks: Block[]; withRecord: boolean }) {
  return (
    <div className="text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
      {blocks.map((block, i) => {
        switch (block.kind) {
          case 'heading':
            return (
              <p key={i} className="mt-[var(--space-8)] font-semibold first:mt-0">
                {block.text}
              </p>
            );
          case 'subheading':
            return (
              <p key={i} className="mt-[var(--space-6)] font-semibold">
                {block.text}
              </p>
            );
          case 'item':
            return (
              <p key={i} className="mt-[var(--space-3)] flex gap-[var(--space-3)]">
                <span aria-hidden="true" className="shrink-0 text-[var(--site-muted)] nums-tabular">
                  {block.ordinal ? `${block.ordinal}.` : '·'}
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
const LABELS = (['VERIFIED', 'HYPOTHESIS', 'UNKNOWN'] as const satisfies readonly EpistemicLabel[])
  .map((label) => {
    const n = RUN.synthesis.reduce(
      (sum, b) =>
        sum + (b.kind === 'para' || b.kind === 'item' ? b.segments.filter((s) => s.kind === 'label' && s.label === label).length : 0),
      0,
    );
    return n ? `${n} ${label.toLowerCase()}` : '';
  })
  .filter(Boolean)
  .join(', ');

const RAIL: Array<{ term: string; value: string }> = [
  { term: 'Sources cited', value: `${RUN.citations.length}, each linked` },
  { term: 'Claims labelled', value: LABELS || 'none' },
  { term: 'Positions argued', value: `${RUN.scores.length}: ${RETAINED} kept, ${PRUNED} pruned` },
  { term: 'Bias flags raised', value: String(BIAS_FLAGS) },
  {
    term: 'Adversarial tests',
    value: RUN.stress.map((t) => `${Math.round(t.survivalRate * 100)}%`).join(', ') + ' survival',
  },
  { term: 'Models involved', value: `${RUN_MODELS.length} from competing labs` },
  { term: 'Cost of the run', value: `$${RUN.ledger.costUsd.toFixed(4)}` },
];

export function ApparatusToggle() {
  const [withRecord, setWithRecord] = useState(true);
  const reduced = usePrefersReducedMotion();
  const groupId = useId();

  return (
    <figure
      data-ui
      className="w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] text-[var(--site-ink)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
        <span id={groupId} className="font-semibold">
          The synthesis
        </span>
        <div role="group" aria-labelledby={groupId} className="flex rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]">
          {[
            { label: 'Answer only', on: false },
            { label: 'With the record', on: true },
          ].map(({ label, on }) => (
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

      <div className="grid lg:grid-cols-3">
        {/* Keyed on the mode so the switch re-runs the entrance keyframe: the
            apparatus visibly arrives rather than blinking into place. Reduced
            motion drops the key, so the text simply changes. */}
        {/* A fragment, not the page: the answer scrolls inside its own reader
            (focusable, so it scrolls from the keyboard) rather than running
            on for screens. Headings inside it are set as bold paragraphs for
            the same reason: the page's outline belongs to the page. */}
        <div
          key={reduced ? 'static' : String(withRecord)}
          role="region"
          aria-label="Synthesis text"
          tabIndex={0}
          className={`max-h-[var(--site-reader-h)] overflow-y-auto p-[var(--space-6)] lg:col-span-2 ${reduced ? '' : 'animate-fade-up'}`}
        >
          <SynthesisBlocks blocks={RUN.synthesis} withRecord={withRecord} />
        </div>

        <dl
          aria-live="polite"
          className="border-t border-[var(--site-line)] bg-[var(--site-surface)] p-[var(--space-6)] lg:border-l lg:border-t-0"
        >
          {RAIL.map(({ term, value }) => (
            <div key={term} className="mb-[var(--space-4)] last:mb-0">
              <dt className="text-[var(--site-muted)]">{term}</dt>
              <dd className={`font-semibold nums-tabular ${withRecord ? '' : 'text-[var(--site-muted)]'}`}>
                {withRecord ? value : '—'}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </figure>
  );
}
