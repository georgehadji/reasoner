import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Server-rendered markdown for documentation pages.
 *
 * Deliberately not a client component: the prose must exist in the first HTML
 * response so crawlers and AI answer engines can read it without executing
 * JavaScript. Styling is explicit per element rather than via a typography
 * plugin, which this project does not install.
 */

interface DocMarkdownProps {
  children: string;
}

export function DocMarkdown({ children }: DocMarkdownProps) {
  return (
    <div className="text-[16px] leading-[1.75] text-[var(--text-2)]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ children: c }) => (
            <h2 className="mt-12 mb-4 scroll-mt-24 text-2xl font-bold tracking-tight text-[var(--text)]">
              {c}
            </h2>
          ),
          h3: ({ children: c }) => (
            <h3 className="mt-8 mb-3 scroll-mt-24 text-lg font-semibold text-[var(--text)]">
              {c}
            </h3>
          ),
          p: ({ children: c }) => <p className="my-4">{c}</p>,
          ul: ({ children: c }) => (
            <ul className="my-4 list-disc space-y-2 pl-6 marker:text-[var(--text-muted)]">{c}</ul>
          ),
          ol: ({ children: c }) => (
            <ol className="my-4 list-decimal space-y-2 pl-6 marker:text-[var(--text-muted)]">{c}</ol>
          ),
          li: ({ children: c }) => <li className="pl-1">{c}</li>,
          strong: ({ children: c }) => (
            <strong className="font-semibold text-[var(--text)]">{c}</strong>
          ),
          a: ({ href, children: c }) => {
            const target = href || '#';
            const isInternal = target.startsWith('/');
            const className =
              'font-medium text-[var(--accent)] underline decoration-[var(--accent)]/30 underline-offset-4 transition-colors hover:decoration-[var(--accent)]';
            return isInternal ? (
              <Link href={target} className={className}>
                {c}
              </Link>
            ) : (
              <a href={target} className={className} rel="noopener noreferrer">
                {c}
              </a>
            );
          },
          blockquote: ({ children: c }) => (
            <blockquote className="my-6 border-l-2 border-[var(--accent)] bg-[var(--surface)] py-1 pl-5 text-[var(--text-muted)]">
              {c}
            </blockquote>
          ),
          code: ({ className, children: c }) => {
            const isBlock = Boolean(className?.startsWith('language-'));
            if (!isBlock) {
              return (
                <code className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[13px] text-[var(--text)]">
                  {c}
                </code>
              );
            }
            return <code className="font-mono text-[13px] leading-relaxed">{c}</code>;
          },
          pre: ({ children: c }) => (
            <pre className="my-6 overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4 text-[var(--text)]">
              {c}
            </pre>
          ),
          table: ({ children: c }) => (
            <div className="my-6 overflow-x-auto rounded-xl border border-[var(--border)]">
              <table className="w-full border-collapse text-left text-[15px]">{c}</table>
            </div>
          ),
          thead: ({ children: c }) => <thead className="bg-[var(--surface-2)]">{c}</thead>,
          th: ({ children: c }) => (
            <th className="border-b border-[var(--border)] px-4 py-3 font-semibold text-[var(--text)]">
              {c}
            </th>
          ),
          td: ({ children: c }) => (
            <td className="border-b border-[var(--border)] px-4 py-3 align-top">{c}</td>
          ),
          hr: () => <hr className="my-10 border-[var(--border)]" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
