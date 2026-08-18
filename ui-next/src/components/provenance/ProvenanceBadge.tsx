'use client';

import { useState } from 'react';
import { Eraser } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SynthesisProvenanceReport } from '@/lib/types';
import { totalRemoved } from '@/lib/provenance';
import { ProvenanceReport } from './ProvenanceReport';

interface ProvenanceBadgeProps {
  report: SynthesisProvenanceReport;
  className?: string;
}

/** Inline chip on a synthesis result -- opens the full findings on click.
 *
 * Always rendered when a report exists, including the zero-findings case:
 * "nothing found" is itself a verifiable, worth-showing result (§10.1 of
 * the integration plan), not something to hide for lack of a headline.
 */
export function ProvenanceBadge({ report, className }: ProvenanceBadgeProps) {
  const [isOpen, setIsOpen] = useState(false);
  const total = totalRemoved(report);

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={cn(
          'inline-flex min-h-[var(--space-8)] items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--chip-bg-2,var(--surface))] px-2.5 py-1 text-[length:var(--text-2xs)] font-medium text-[var(--text-2)] transition-colors hover:bg-[var(--surface-3)]',
          className
        )}
      >
        <Eraser className="h-3 w-3" aria-hidden="true" />
        {total > 0 ? `${total} carrier${total === 1 ? '' : 's'} removed` : 'No hidden characters found'}
      </button>

      <ProvenanceReport isOpen={isOpen} onClose={() => setIsOpen(false)} report={report} />
    </>
  );
}
