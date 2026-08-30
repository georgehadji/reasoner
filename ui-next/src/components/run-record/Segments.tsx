import type { Segment } from '@/lib/demo-record';
import { EPISTEMIC_TAG, epistemicClassName } from '@/lib/remark-epistemic';

/**
 * Renders one run of parsed inline segments.
 *
 * Deliberately has no `'use client'`: the same renderer is used by the server
 * -rendered position excerpts and by the client-side apparatus toggle, and the
 * only reason those two would ever diverge is a bug.
 *
 * `withRecord = false` drops apparatus segments — citations and epistemic
 * labels — entirely rather than hiding them, because the point of that mode is
 * to show what an answer looks like when the provenance was never kept.
 */

const MARK_CLASS: Record<string, string> = EPISTEMIC_TAG;

interface MarksProps {
  segments: readonly Segment[];
  withRecord?: boolean;
}

export function Marks({ segments, withRecord = true }: MarksProps) {
  return (
    <>
      {segments.map((segment, i) => {
        switch (segment.kind) {
          case 'text':
            return <span key={i}>{segment.text}</span>;

          case 'strong':
            return (
              <strong key={i} className="font-semibold text-[var(--text)]">
                {segment.text}
              </strong>
            );

          case 'label':
            if (!withRecord) return null;
            return (
              <span
                key={i}
                className={epistemicClassName(MARK_CLASS[segment.label])}
              >
                {segment.label}
                {segment.qualifier ? ` ${segment.qualifier}` : ''}
              </span>
            );

          case 'cite':
            if (!withRecord) return null;
            return (
              <a
                key={i}
                href={segment.url}
                target="_blank"
                rel="noopener noreferrer"
                title={segment.domain}
                className="nums-tabular ml-[1px] align-super font-mono text-[length:var(--text-2xs)] text-[var(--accent)] underline decoration-dotted underline-offset-2 hover:text-[var(--accent-hover)]"
              >
                {segment.index}
              </a>
            );
        }
      })}
    </>
  );
}
