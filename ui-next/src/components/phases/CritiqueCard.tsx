'use client';

import { cn } from '@/lib/utils';
import { Star } from 'lucide-react';

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
    <div className="space-y-4">
      {criticScores.map((cs: Record<string, unknown>, idx: number) => {
        const criticId = typeof cs.critic_id === 'string' ? cs.critic_id : '?';
        const criticModel = typeof cs.critic_model === 'string' ? cs.critic_model : '';
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const candidateScores = cs.candidate_scores as Record<string, any>;
        const dissentingNote = typeof cs.dissenting_note === 'string' ? cs.dissenting_note : '';

        return (
          <div
            key={`critic-${idx}`}
            className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3"
          >
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-base font-medium text-[var(--text)]">
                {criticId}
              </span>
              {criticModel && (
                <span className="text-sm font-mono text-[var(--text-subtle)]">
                  {criticModel.split('/').pop() || criticModel}
                </span>
              )}
            </div>

            {candidateScores && typeof candidateScores === 'object' && (
              <div className="space-y-2 mt-2">
                {Object.entries(candidateScores).map(([genId, dims], i) => {
                  const total = typeof dims.total === 'number' ? dims.total : 0;
                  const barWidth = Math.min(100, total * 10); // assuming 0-10 scale
                  
                  return (
                    <div key={i} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-[var(--text-muted)]">{genId}</span>
                        <span className="font-mono font-semibold text-[var(--text)]">{total.toFixed(1)}</span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-3)]">
                        <div
                          className="h-full rounded-full bg-[var(--accent)] transition-all"
                          style={{ width: `${barWidth}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {dissentingNote && (
              <div className="mt-3 text-sm text-[var(--text-muted)] border-t border-[var(--border)] pt-2">
                <span className="font-medium text-yellow-500/80">Dissenting Note:</span>{' '}
                {dissentingNote}
              </div>
            )}
          </div>
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
        const barWidth = Math.min(100, total);

        return (
          <div
            key={idx}
            className={cn(
              'rounded-xl border p-3',
              isTop
                ? 'border-[var(--accent)]/30 bg-[var(--accent)]/5'
                : 'border-[var(--border)] bg-[var(--surface)]'
            )}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-base font-medium text-[var(--text)]">
                  {perspective}
                </span>
                {isTop && (
                  <span className="flex items-center gap-1 rounded-full bg-[var(--accent)] px-2 py-0.5 text-sm font-medium text-[var(--accent-text)]">
                    <Star className="h-3.5 w-3.5" /> Top
                  </span>
                )}
              </div>
              <span className="font-mono text-base font-semibold text-[var(--text)]">
                {total.toFixed(1)}
              </span>
            </div>

            <div className="mt-2 flex items-center gap-3">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
                <div
                  className="h-full rounded-full bg-[var(--accent)] transition-all"
                  style={{ width: `${barWidth}%` }}
                />
              </div>
            </div>

            {biasFlags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {biasFlags.map((b: string, i: number) => (
                  <span
                    key={i}
                    className="rounded-full border border-red-500/20 bg-red-500/10 px-2 py-0.5 text-sm text-red-500"
                  >
                    {b}
                  </span>
                ))}
              </div>
            )}

            {steelMan && (
              <div className="mt-2 text-sm text-[var(--text-muted)]">
                <span className="font-medium text-[var(--text-subtle)]">Steel man:</span>{' '}
                {steelMan}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
