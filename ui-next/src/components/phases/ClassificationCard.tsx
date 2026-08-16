'use client';

import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { TEXT_SIZES } from '@/lib/config';

interface ClassificationCardProps {
  data: unknown;
}

export function ClassificationCard({ data }: ClassificationCardProps) {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;

  const taskType = typeof d.task_type === 'string' ? d.task_type : null;
  const rationale = typeof d.rationale === 'string' ? d.rationale : '';
  const language = typeof d.language === 'string' ? d.language : null;
  const tokens = d.tokens as { input?: number; output?: number } | undefined;

  // Each task type gets a distinct, theme-safe treatment: text at the full
  // semantic token, background at a ~10% wash of it. Within a shared hue the
  // second type adds an inset ring so the pair stays distinguishable.
  const badgeColor: Record<string, string> = {
    analytical:
      'bg-[color-mix(in_oklab,var(--accent)_10%,transparent)] text-[var(--accent)]',
    technical:
      'bg-[color-mix(in_oklab,var(--accent)_10%,transparent)] text-[var(--accent)] ring-1 ring-inset ring-[color-mix(in_oklab,var(--accent)_35%,transparent)]',
    strategic:
      'bg-[color-mix(in_oklab,var(--warn)_10%,transparent)] text-[var(--warn)]',
    predictive:
      'bg-[color-mix(in_oklab,var(--warn)_10%,transparent)] text-[var(--warn)] ring-1 ring-inset ring-[color-mix(in_oklab,var(--warn)_35%,transparent)]',
    creative:
      'bg-[color-mix(in_oklab,var(--ok)_10%,transparent)] text-[var(--ok)]',
    hybrid:
      'bg-[color-mix(in_oklab,var(--unknown)_10%,transparent)] text-[var(--unknown)]',
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {taskType && (
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              badgeColor[taskType.toLowerCase()] || 'bg-[var(--surface-3)] text-[var(--text)]'
            }`}
          >
            {taskType}
          </span>
        )}
        {language && (
          <span className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs text-[var(--text-muted)]">
            {language}
          </span>
        )}
      </div>

      {rationale && (
        <div className={`${TEXT_SIZES.phaseCard} text-[var(--text-2)]`}>
          <MarkdownRenderer>{rationale}</MarkdownRenderer>
        </div>
      )}

      {/* Tokens shown in PhaseCard header */}
    </div>
  );
}
