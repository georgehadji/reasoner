'use client';

import { memo, useMemo } from 'react';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { TEXT_SIZES } from '@/lib/config';

interface Citation {
  index: number;
  title: string;
  url: string;
}

interface SynthesisRendererProps {
  text: string;
  className?: string;
}

/**
 * Converts inline markdown links [title](url) into academic footnote-style
 * citations. Footnote marks [^1], [^2]… appear inline; the reference list
 * is appended at the very end of the document.
 */
export const SynthesisRenderer = memo(function SynthesisRenderer({
  text,
  className = TEXT_SIZES.synthesis,
}: SynthesisRendererProps) {
  const { body, footnotes } = useMemo(() => {
    const citations: Citation[] = [];
    const seen = new Map<string, number>(); // url -> index

    // Replace each [title](url) with title[^index]
    const body = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (match, title, url) => {
      let idx = seen.get(url);
      if (idx === undefined) {
        idx = citations.length + 1;
        seen.set(url, idx);
        citations.push({ index: idx, title: title.trim(), url });
      }
      return `${title}[^${idx}]`;
    });

    return { body, footnotes: citations };
  }, [text]);

  return (
    <div className={`markdown-body ${className}`}>
      <MarkdownRenderer>{body}</MarkdownRenderer>

      {footnotes.length > 0 && (
        <section className="mt-8 border-t border-[var(--border)] pt-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
            References
          </h3>
          <ol className="space-y-2 text-sm text-[var(--text)]">
            {footnotes.map((c) => (
              <li key={c.index} id={`ref-${c.index}`} className="flex gap-2">
                <sup className="mt-0.5 text-[10px] text-[var(--text-subtle)]">[{c.index}]</sup>
                <span>
                  {c.title}.{' '}
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline text-[var(--text-subtle)] hover:text-[var(--accent)]"
                  >
                    {c.url}
                  </a>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
});
