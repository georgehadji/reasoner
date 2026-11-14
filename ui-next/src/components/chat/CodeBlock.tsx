'use client';

import { useState, useMemo } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Check, Copy } from 'lucide-react';
import { TIMING } from '@/lib/config';
import { copyToClipboard } from '@/lib/utils';

/**
 * Heavily-lazy loaded syntax-highlighted code block.
 * This entire file (~400KB with Prism) is split into its own JS chunk
 * and only loaded when a code block appears in markdown.
 */
export function CodeBlock({
  code,
  language,
}: {
  code: string;
  language: string;
}) {
  const [copied, setCopied] = useState(false);
  // Always the dark palette: every page that renders markdown is `.site`,
  // charcoal in both colour schemes, so a light system scheme no longer means
  // a light page.
  const customStyle = useMemo(() => ({ margin: 0, padding: '1em', background: 'transparent', fontSize: '0.85em' }), []);

  async function handleCopy() {
    const ok = await copyToClipboard(code);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), TIMING.copiedFeedbackMs);
    }
  }

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span className="uppercase tracking-wide">{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[length:var(--text-xs)] transition-colors hover:bg-[var(--surface-3)]"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5" /> Copied
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" /> Copy
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={vscDarkPlus}
        customStyle={customStyle}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
