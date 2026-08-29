'use client';

import { cn } from '@/lib/utils';
import { AlertTriangle } from 'lucide-react';
import { ICON_SM, ScoreMeter } from './PhaseCard';
import { ScoreMatrix } from '@/components/run-record/ScoreMatrix';
import type { RunScore } from '@/lib/demo-record';

interface CritiqueCardProps {
  data: unknown;
}

export function CritiqueCard({ data }: CritiqueCardProps) {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const scores = Array.isArray(d.scores) ? d.scores : [];
  const criticScores = Array.isArray(d.critic_scores) ? d.critic_scores : [];

  if (!scores.length && !criticScores.length) return null;

  /* Live payload is snake_case; RunScore is camelCase. `retained` has no live
     equivalent — the backend only marks the single winner — so is_top is the
     honest mapping: one column carried forward, the rest shown as pruned. */
  const num = (v: unknown): number => (typeof v === 'number' ? v : 0);
  const matrixScores: RunScore[] = scores.map((raw) => {
    const s = raw as Record<string, unknown>;
    return {
      position:
        typeof s.perspective === 'string'
          ? s.perspective
          : (s.perspective as Record<string, string>)?.name ?? '?',
      logicalConsistency: num(s.logical_consistency),
      evidenceSupport: num(s.evidence_support),
      failureResilience: num(s.failure_resilience),
      feasibility: num(s.feasibility),
      total: num(s.total),
      biasFlags: Array.isArray(s.bias_flags) ? (s.bias_flags as string[]) : [],
      steelMan: typeof s.steel_man === 'string' ? s.steel_man : '',
      retained: !!s.is_top,
    };
  });
  const steelManned = matrixScores.filter((m) => m.steelMan);

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

      {/* The signature figure, not a card stack: rivals across the columns,
          axes down the rows, and the positions the run threw away shown in
          place and greyed rather than quietly omitted. A stack of cards
          structurally cannot show the comparison this table IS.
          Same backend data — see spec/art-direction.md migration step 4. */}
      {matrixScores.length > 0 && (
        <ScoreMatrix
          scores={matrixScores}
          caption="Independent scoring of every position, 0-10 per axis. Pruned positions stay in the table."
        />
      )}

      {/* steel_man is prose and does not fit a numeric cell, so the strongest
          form of each REJECTED argument is kept below the table. Preserving
          what the run argued against is the point of showing the losers. */}
      {steelManned.length > 0 && (
        <dl className="flow [--flow-space:var(--space-2)] border-t border-[var(--border)] pt-[var(--space-3)]">
          {steelManned.map(({ position, steelMan, retained }) => (
            <div key={position}>
              <dt className="font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                {position}
                {!retained && (
                  <span className="ml-[var(--space-2)] font-normal text-[var(--text-subtle)]">
                    pruned — steel man
                  </span>
                )}
              </dt>
              <dd className="m-0 text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                {steelMan}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
