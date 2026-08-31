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

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {taskType && (
          // Task type is a label, not a status — one neutral pill for every
          // category. --ok/--warn/--unknown are reserved for epistemic
          // labels, and the word itself already distinguishes "Strategic"
          // from "Creative"; a per-type hue was decoration, not information.
          <span className="rounded-full bg-[var(--surface-3)] px-2.5 py-1 text-[length:var(--text-xs)] font-medium text-[var(--text)]">
            {taskType}
          </span>
        )}
        {language && (
          <span className="rounded-full border border-[var(--border)] px-2.5 py-1 text-[length:var(--text-xs)] text-[var(--text-muted)]">
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
