import type { ReactNode } from 'react';
import { REVIEW_STATUS_LABEL, type ReviewStatus } from '@/lib/sectors';

/**
 * One panel listing questions or controls, each row led by its status. Rows
 * part by space alone: a box per row read as a stack of identical cards.
 * The status carries three signals (word, rule style, ink) so it survives
 * monochrome printing. Shared by the home page's sector tabs and /security.
 */
export const STATUS_RULE: Record<ReviewStatus, string> = {
  available: 'epistemic-verified',
  'to-confirm': 'epistemic-unknown',
  'not-available': 'border-l-2 border-[var(--site-muted)] text-[var(--site-muted)]',
};

export interface StatusBand {
  title: string;
  status: ReviewStatus;
  detail: ReactNode;
}

export function StatusBands({ items, className = '' }: { items: readonly StatusBand[]; className?: string }) {
  return (
    <ul className={`list-none rounded-[var(--site-radius)] bg-[var(--site-surface)] py-[var(--space-2)] ${className}`}>
      {items.map(({ title, status, detail }) => (
        <li
          key={title}
          className="grid gap-[var(--space-2)] px-[var(--space-5)] py-[var(--space-4)] lg:grid-cols-[var(--site-tab)_minmax(0,1fr)] lg:gap-[var(--space-6)]"
        >
          <span className={`${STATUS_RULE[status]} self-start pl-[var(--space-2)] text-[length:var(--site-small)] font-semibold`}>
            {REVIEW_STATUS_LABEL[status]}
          </span>
          <span>
            <span className="block text-[length:var(--site-body)] font-semibold leading-[var(--lh-ui)]">{title}</span>
            <span className="mt-[var(--space-1)] block text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
              {detail}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
