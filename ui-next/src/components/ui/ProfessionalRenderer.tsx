'use client';

import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { github } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import { FC, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import { cn } from '@/lib/utils';

// Helper to check for hex color validity
const isHexColor = (hex: string) => /^#([0-9A-F]{3}){1,2}$/i.test(hex);

interface ProfessionalRendererProps {
  content: string;
  className?: string;
  layoutHints?: {
    primary_theme_color?: string;
    important_sections?: string[];
  };
}

export const ProfessionalRenderer: FC<ProfessionalRendererProps> = ({ content, className, layoutHints }) => {
  const validThemeColor = layoutHints?.primary_theme_color && isHexColor(layoutHints.primary_theme_color)
    ? layoutHints.primary_theme_color
    : 'var(--accent)';

  const components = useMemo<Components>(() => ({
    h1: ({ ...props }) => <h1 className="mb-4 mt-2 border-b-2 pb-2 text-3xl font-bold" style={{ borderColor: validThemeColor }} {...props} />,
    h2: ({ ...props }) => <h2 className="mb-3 mt-4 border-b pb-2 text-2xl font-semibold" {...props} />,
    h3: ({ ...props }) => <h3 className="mb-3 mt-4 text-xl font-semibold" {...props} />,
    p: ({ ...props }) => <p className="mb-4 leading-relaxed text-[var(--text-muted)]" {...props} />,
    ul: ({ ...props }) => <ul className="mb-4 ml-6 list-disc [&>li]:mt-2" {...props} />,
    ol: ({ ...props }) => <ol className="mb-4 ml-6 list-decimal [&>li]:mt-2" {...props} />,
    a: ({ ...props }) => <a className="font-medium text-[var(--accent)] underline" {...props} />,
    blockquote: ({ ...props }) => <blockquote className="mt-6 border-l-4 pl-4 italic" style={{ borderColor: validThemeColor }} {...props} />,
    code: ({ className, children }) => {
      const match = /language-(\w+)/.exec(className || '');
      return match ? (
        <SyntaxHighlighter style={github} language={match[1]} PreTag="div">
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 font-mono text-sm text-[var(--text)]">
          {children}
        </code>
      );
    },
  }), [validThemeColor]);

  return (
    <div className={cn('prose prose-stone max-w-none dark:prose-invert', className)}>
      <ReactMarkdown
        components={components}
        remarkPlugins={[remarkGfm]}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
