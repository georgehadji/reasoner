import Link from 'next/link';
import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Server-rendered markdown for documentation pages, in the site world
 * "The product performs".
 *
 * Deliberately not a client component: the prose must exist in the first HTML
 * response so crawlers and AI answer engines can read it without executing
 * JavaScript. Styling is explicit per element rather than via a typography
 * plugin, which this project does not install. Tables and code blocks are the
 * interface on a guide, so each is framed as a fragment (data-ui).
 */

/** "The stream stops mid-run" → "the-stream-stops-mid-run", so a heading can be linked to. */
export function docAnchor(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (node && typeof node === 'object' && 'props' in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return '';
}

const FRAME = 'my-[var(--space-6)] overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)]';
const CELL = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] align-top';

export function DocMarkdown({ children }: { children: string }) {
  return (
    <div className="text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children: c }) => (
            <h2
              data-reveal
              id={docAnchor(textOf(c))}
              className="mt-[var(--space-16)] mb-[var(--space-4)] scroll-mt-[var(--site-sticky-top)] font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)]"
            >
              {c}
            </h2>
          ),
          h3: ({ children: c }) => (
            <h3
              id={docAnchor(textOf(c))}
              className="mt-[var(--space-10)] mb-[var(--space-3)] scroll-mt-[var(--site-sticky-top)] font-semibold"
            >
              {c}
            </h3>
          ),
          p: ({ children: c }) => <p className="my-[var(--space-4)] max-w-[68ch]">{c}</p>,
          ul: ({ children: c }) => (
            <ul className="my-[var(--space-4)] max-w-[68ch] list-disc space-y-[var(--space-2)] pl-[var(--space-6)] marker:text-[var(--site-muted)]">
              {c}
            </ul>
          ),
          ol: ({ children: c }) => (
            <ol className="my-[var(--space-4)] max-w-[68ch] list-decimal space-y-[var(--space-2)] pl-[var(--space-6)] marker:text-[var(--site-muted)]">
              {c}
            </ol>
          ),
          strong: ({ children: c }) => <strong className="font-semibold">{c}</strong>,
          a: ({ href, children: c }) => {
            const target = href || '#';
            return target.startsWith('/') ? (
              <Link href={target} className="site-link text-current">
                {c}
              </Link>
            ) : (
              <a href={target} className="site-link text-current" rel="noopener noreferrer">
                {c}
              </a>
            );
          },
          blockquote: ({ children: c }) => (
            <blockquote className="my-[var(--space-6)] max-w-[68ch] border-l-2 border-[var(--site-accent)] pl-[var(--space-5)] text-[var(--site-muted)]">
              {c}
            </blockquote>
          ),
          code: ({ className, children: c }) =>
            className?.startsWith('language-') ? (
              <code className="font-mono">{c}</code>
            ) : (
              <code className="rounded-[var(--radius-sm)] bg-[var(--site-surface-2)] px-[var(--space-1)] font-mono">{c}</code>
            ),
          // Both scroll sideways on a phone; tabIndex lets a keyboard user scroll them.
          pre: ({ children: c }) => (
            <pre tabIndex={0} data-ui data-reveal className={`${FRAME} p-[var(--space-4)] text-[length:var(--site-small)]`}>
              {c}
            </pre>
          ),
          table: ({ children: c }) => (
            <div role="region" aria-label="Table" tabIndex={0} data-ui data-reveal className={FRAME}>
              <table className="w-full border-collapse text-left text-[length:var(--site-small)]">{c}</table>
            </div>
          ),
          th: ({ children: c }) => <th className={`${CELL} font-semibold`}>{c}</th>,
          td: ({ children: c }) => <td className={CELL}>{c}</td>,
          hr: () => <hr className="my-[var(--space-12)] border-[var(--site-line)]" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
