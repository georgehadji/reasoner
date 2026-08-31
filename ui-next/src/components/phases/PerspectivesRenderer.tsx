import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { epistemicClassName, extractEpistemicMarks } from '@/lib/remark-epistemic';

/**
 * Perspectives phase (phase 2): each generated position carries its own
 * inline epistemic labels — labelling starts here, not at synthesis (see
 * `demo-record.ts`'s docblock on `RunPosition.excerpt`). Prose still renders
 * through `MarkdownRenderer`, whose `remarkEpistemic` plugin marks the same
 * labels inline; this adds a marginal gutter per position summarizing them,
 * since a position can carry six labels in a paragraph a reader skims once.
 */

interface Candidate {
  perspective: string;
  content: string;
  key_insights: string[];
  model_used?: string;
}

export function PerspectivesRenderer({ candidates }: { candidates: Candidate[] }) {
  if (!candidates.length) return null;

  return (
    <div className="space-y-[var(--space-6)]">
      {candidates.map((c, i) => {
        const marks = extractEpistemicMarks(c.content);
        const model = c.model_used ? c.model_used.split('/').pop() : '';
        return (
          <article key={i} className="grid grid-cols-1 gap-[var(--space-4)] lg:grid-cols-[1fr_auto]">
            <div className="min-w-0">
              <h4 className="mb-[var(--space-2)] text-[length:var(--text-sm)] font-semibold capitalize text-[var(--text)]">
                {c.perspective}
                {model && (
                  <span className="ml-[var(--space-2)] font-normal text-[var(--text-subtle)]">
                    {model}
                  </span>
                )}
              </h4>
              <div className="markdown-body">
                <MarkdownRenderer>{c.content}</MarkdownRenderer>
              </div>
              {c.key_insights.length > 0 && (
                <ul className="mt-[var(--space-2)] list-disc space-y-1 pl-5 text-[length:var(--text-sm)] text-[var(--text)]">
                  {c.key_insights.map((insight, ii) => (
                    <li key={ii}>{insight}</li>
                  ))}
                </ul>
              )}
            </div>
            {marks.length > 0 && (
              <aside
                aria-label={`Epistemic labels for ${c.perspective}`}
                className="flex shrink-0 flex-row flex-wrap gap-[var(--space-1)] border-t border-[var(--border)] pt-[var(--space-2)] lg:w-40 lg:flex-col lg:border-l lg:border-t-0 lg:pl-[var(--space-4)] lg:pt-0"
              >
                {marks.map((mark, mi) => (
                  <span key={mi} className={epistemicClassName(`epistemic-${mark.label.toLowerCase()}`)}>
                    {mark.label}
                    {mark.qualifier ? ` ${mark.qualifier}` : ''}
                  </span>
                ))}
              </aside>
            )}
          </article>
        );
      })}
    </div>
  );
}
