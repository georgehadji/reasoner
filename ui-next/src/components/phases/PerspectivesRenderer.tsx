import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { epistemicClassName, extractEpistemicMarks } from '@/lib/remark-epistemic';

/**
 * Perspectives phase (phase 2): each generated position carries its own
 * inline epistemic labels — labelling starts here, not at synthesis (see
 * `demo-record.ts`'s docblock on `RunPosition.excerpt`). Prose still renders
 * through `MarkdownRenderer`, whose `remarkEpistemic` plugin marks the same
 * labels inline; this adds one count line per position summarizing them,
 * since a position can carry six labels in a paragraph a reader skims once.
 * Counts, not the labels again: a gutter repeating every label in order said
 * nothing the paragraph had not.
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
        const counts = extractEpistemicMarks(c.content).reduce(
          (m, { label }) => m.set(label, (m.get(label) ?? 0) + 1),
          new Map<string, number>(),
        );
        const model = c.model_used ? c.model_used.split('/').pop() : '';
        return (
          // .misregister: each position prints on its own pink plate,
          // offset differently, never in register with the others.
          <article key={i} className="misregister border border-[var(--border-strong)] bg-[var(--surface)] p-[var(--space-4)]">
            <div className="min-w-0">
              <h4 className="mb-[var(--space-2)] text-[length:var(--text-sm)] font-semibold capitalize text-[var(--text)]">
                {c.perspective}
                {model && (
                  <span className="ml-[var(--space-2)] font-normal text-[var(--text-subtle)]">
                    {model}
                  </span>
                )}
              </h4>
              {counts.size > 0 && (
                <p className="mb-[var(--space-3)] flex flex-wrap gap-x-[var(--space-3)] gap-y-[var(--space-1)] text-[length:var(--text-xs)] text-[var(--text-muted)]">
                  {[...counts].map(([label, n]) => (
                    <span key={label}>
                      {n}
                      <span className={epistemicClassName(`epistemic-${label.toLowerCase()}`)}>{label}</span>
                    </span>
                  ))}
                </p>
              )}
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
          </article>
        );
      })}
    </div>
  );
}
