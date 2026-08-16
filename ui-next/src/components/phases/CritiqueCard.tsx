'use client';

import { cn } from '@/lib/utils';
import { Star, AlertTriangle, Shield } from 'lucide-react';
import { ICON_SM, MICRO_LABEL, ScoreMeter } from './PhaseCard';

interface CritiqueCardProps {
  data: unknown;
}

export function CritiqueCard({ data }: CritiqueCardProps) {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const scores = Array.isArray(d.scores) ? d.scores : [];
  const criticScores = Array.isArray(d.critic_scores) ? d.critic_scores : [];

  if (!scores.length && !criticScores.length) return null;

  return (
    <div className="flow [--flow-space:var(--space-4)]">
      {criticScores.map((cs: Record<string, unknown>, idx: number) => {
        const criticId = typeof cs.critic_id === 'string' ? cs.critic_id : '?';
        const criticModel = typeof cs.critic_model === 'string' ? cs.critic_model : '';
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const candidateScores = cs.candidate_scores as Record<string, any>;
        const dissentingNote = typeof cs.dissenting_note === 'string' ? cs.dissenting_note : '';

        return (
          <article
            key={`critic-${idx}`}
            className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-3)]"
          >
            <div className="mb-[var(--space-2)] flex flex-wrap items-baseline justify-between gap-[var(--space-3)]">
              <h3 className="text-[length:var(--text-lg)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
                {criticId}
              </h3>
              {criticModel && (
                <span className="font-mono text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
                  {criticModel.split('/').pop() || criticModel}
                </span>
              )}
            </div>

            {candidateScores && typeof candidateScores === 'object' && (
              <dl className="flow [--flow-space:var(--space-2)]">
                {Object.entries(candidateScores).map(([genId, dims], i) => {
                  const total = typeof dims.total === 'number' ? dims.total : 0;

                  return (
                    // HTML allows `dl > div` only when that div DIRECTLY holds
                    // the dt/dd pair. They were one level deeper with a <span>
                    // sibling, so parsers discarded the list semantics. Grid
                    // gives the same baseline row without the extra element,
                    // and the meter moves inside the <dd> it describes.
                    <div
                      key={i}
                      className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)]"
                    >
                      <dt className="min-w-0 truncate text-[var(--text-muted)]">{genId}</dt>
                      <dd className="nums-tabular col-start-2 m-0 shrink-0 font-semibold text-[var(--text)]">
                        {total.toFixed(1)}
                        <span className="font-normal text-[var(--text-muted)]">/10</span>
                      </dd>
                      <dd className="col-span-2 m-0 mt-[var(--space-1)]">
                        <ScoreMeter value={total} max={10} className="w-full" />
                      </dd>
                    </div>
                  );
                })}
              </dl>
            )}

            {dissentingNote && (
              <p className="mt-[var(--space-3)] border-t border-[var(--border)] pt-[var(--space-2)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                <span className="mr-[var(--space-1)] inline-flex items-center gap-[var(--space-1)] font-medium text-[var(--warn)]">
                  <AlertTriangle aria-hidden="true" className={ICON_SM} />
                  Dissenting note:
                </span>
                {dissentingNote}
              </p>
            )}
          </article>
        );
      })}

      {scores.map((s: Record<string, unknown>, idx: number) => {
        const perspective =
          typeof s.perspective === 'string'
            ? s.perspective
            : (s.perspective as Record<string, string>)?.name ?? '?';
        const total = typeof s.total === 'number' ? s.total : 0;
        const isTop = !!s.is_top;
        const biasFlags = Array.isArray(s.bias_flags) ? s.bias_flags : [];
        const steelMan = typeof s.steel_man === 'string' ? s.steel_man : '';

        return (
          <article
            key={idx}
            className={cn(
              'rounded-[var(--radius-lg)] border p-[var(--space-3)]',
              isTop
                ? 'border-[var(--accent)] bg-[var(--accent-dim)]'
                : 'border-[var(--border)] bg-[var(--surface)]'
            )}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-[var(--space-3)]">
              <div className="flex min-w-0 items-center gap-[var(--space-2)]">
                <h3 className="truncate text-[length:var(--text-lg)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
                  {perspective}
                </h3>
                {isTop && (
                  <span
                    className={cn(
                      MICRO_LABEL,
                      'inline-flex shrink-0 items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] bg-[var(--accent)] px-[var(--space-2)] py-[var(--space-1)] text-[var(--accent-text)]'
                    )}
                  >
                    <Star aria-hidden="true" className={ICON_SM} /> Top
                  </span>
                )}
              </div>
              <span className="nums-tabular shrink-0 text-[length:var(--text-lg)] font-semibold leading-[var(--lh-tight)] text-[var(--text)]">
                {total.toFixed(1)}
                <span className="text-[length:var(--text-sm)] font-normal text-[var(--text-muted)]">/10</span>
              </span>
            </div>

            {/* max=10, not 100. `scores.total` is a mean of four 0-10 dimensions
                minus a penalty (domain/core_types.py CritiqueScores.total), so
                a 100-scale meter rendered an 8.2 as an 8%-full bar. */}
            <ScoreMeter value={total} max={10} className="mt-[var(--space-2)] w-full" />

            {biasFlags.length > 0 && (
              <div className="mt-[var(--space-2)] flex flex-wrap gap-[var(--space-1)]">
                <span className="sr-only">Bias flags:</span>
                {biasFlags.map((b: string, i: number) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] border border-[var(--red-border)] bg-[var(--red-bg)] px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--red)]"
                  >
                    <AlertTriangle aria-hidden="true" className={ICON_SM} />
                    {b}
                  </span>
                ))}
              </div>
            )}

            {steelMan && (
              <p className="mt-[var(--space-2)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                <span className="mr-[var(--space-1)] inline-flex items-center gap-[var(--space-1)] font-medium text-[var(--text-subtle)]">
                  <Shield aria-hidden="true" className={ICON_SM} />
                  Steel man:
                </span>
                {steelMan}
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}
