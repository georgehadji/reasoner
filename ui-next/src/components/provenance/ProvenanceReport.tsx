'use client';

import { createPortal } from 'react-dom';
import { Eraser, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SynthesisProvenanceReport } from '@/lib/types';
import { totalRemoved } from '@/lib/provenance';

interface ProvenanceReportProps {
  isOpen: boolean;
  onClose: () => void;
  report: SynthesisProvenanceReport;
}

/** Detail drawer for a synthesis output's Layer A scrub findings.
 *
 * Copy discipline (docs/plans/watermark-removal-integration.md Part V.7):
 * state only what was verifiably removed -- never "undetectable", never
 * "proves human-written", never "bypasses AI detection".
 */
export function ProvenanceReport({ isOpen, onClose, report }: ProvenanceReportProps) {
  if (!isOpen) return null;
  if (typeof document === 'undefined') return null;

  const total = totalRemoved(report);
  const hits = report.core_solution?.hits ?? [];

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-[var(--scrim)] p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-[var(--width-content,32rem)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-lg)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius)] bg-[color-mix(in_oklab,var(--accent)_12%,transparent)] text-[var(--accent)]">
              <Eraser className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[var(--text)]">Provenance scrub report</h3>
              <p className="text-[length:var(--text-xs)] text-[var(--text-2)]">
                {total > 0
                  ? `${total} invisible character${total === 1 ? '' : 's'} removed from this response`
                  : 'No invisible characters were found in this response'}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close provenance report"
            className="min-touch rounded-[var(--radius)] p-2 text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {hits.length > 0 && (
          <div className="mb-4 overflow-x-auto rounded-[var(--radius)] border border-[var(--border)]">
            <table className="w-full text-left text-[length:var(--text-xs)]">
              <thead className="bg-[var(--surface-2)] text-[var(--text-2)]">
                <tr>
                  <th className="px-3 py-2 font-medium">Carrier</th>
                  <th className="px-3 py-2 font-medium">Kind</th>
                  <th className="px-3 py-2 font-medium">Confidence</th>
                  <th className="px-3 py-2 text-right font-medium">Count</th>
                </tr>
              </thead>
              <tbody>
                {hits.map((hit) => (
                  <tr key={hit.codepoint} className="border-t border-[var(--border)] text-[var(--text)]">
                    <td className="px-3 py-2 font-mono">{hit.label}</td>
                    <td className="px-3 py-2">{hit.kind}</td>
                    <td className="px-3 py-2">{hit.confidence}</td>
                    <td className="nums-tabular px-3 py-2 text-right">{hit.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <dl className="grid grid-cols-3 gap-2 text-[length:var(--text-xs)]">
          <div className={cn('rounded-[var(--radius)] border border-[var(--border)] p-2 text-center')}>
            <dt className="text-[var(--text-2)]">Insights</dt>
            <dd className="nums-tabular font-semibold text-[var(--text)]">
              {report.critical_insights_removed}
            </dd>
          </div>
          <div className={cn('rounded-[var(--radius)] border border-[var(--border)] p-2 text-center')}>
            <dt className="text-[var(--text-2)]">Blueprint</dt>
            <dd className="nums-tabular font-semibold text-[var(--text)]">
              {report.action_blueprint_removed}
            </dd>
          </div>
          <div className={cn('rounded-[var(--radius)] border border-[var(--border)] p-2 text-center')}>
            <dt className="text-[var(--text-2)]">Questions</dt>
            <dd className="nums-tabular font-semibold text-[var(--text)]">
              {report.open_questions_removed}
            </dd>
          </div>
        </dl>

        <p className="mt-4 text-[length:var(--text-2xs)] text-[var(--text-muted)]">
          Covers invisible/edit-based Unicode carriers in this response&apos;s text only. Does not
          cover statistical token-sampling patterns or image pixel-domain marks.
        </p>
      </div>
    </div>,
    document.body
  );
}
