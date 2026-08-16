'use client';

import { useState, useMemo } from 'react';
import { X, Copy, Check, AlertTriangle, AlertCircle, RotateCcw, Pencil } from 'lucide-react';
import { TIMING } from '@/lib/config';
import { copyToClipboard } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';

interface ErrorMessageProps {
  content: string;
  errorType?: string | null;
  retryable?: boolean | null;
  onRetry?: () => void;
  onEditRetry?: () => void;
}

/* Shared shape for the small text buttons in the footer row. 40px minimum
   height is the WCAG 2.5.5 touch target — the icons alone are 14px. */
const ACTION_BUTTON =
  'inline-flex min-h-[var(--space-10)] items-center gap-[var(--space-1)] rounded-[var(--radius-sm)] px-[var(--space-1)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--text)]';

function isWarningContent(content: string): boolean {
  return /warning|citation integrity|vetting flags|skipped|ignored/i.test(content);
}

/** Parses JSON-like error messages to extract a user-friendly string. */
function parseErrorMessage(content: string): { display: string; original: string } {
  try {
    const parsed = JSON.parse(content);
    if (parsed && typeof parsed === 'object') {
      if (parsed.error?.message) return { display: parsed.error.message, original: content };
      if (parsed.detail) return { display: parsed.detail, original: content };
      // Fallback for other common error structures, stringify for display if object
      return { display: JSON.stringify(parsed, null, 2), original: content };
    }
  } catch {
    // Not JSON, or malformed JSON. Continue to other checks.
  }

  // Detect and parse Python tracebacks
  if (content.includes('Traceback (most recent call last):')) {
    const lines = content.split('\n');
    // Find the last line that looks like an error message
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();
      if (line && !line.startsWith('File') && !line.startsWith('  ')) {
        return { display: line, original: content }; // e.g., "AttributeError: 'NoneType' object has no attribute 'foo'"
      }
    }
    return { display: 'An internal server error occurred. Check details for traceback.', original: content };
  }

  // Detect other common Python errors not necessarily with a full traceback header
  if (content.includes('AttributeError:') || content.includes('TypeError:') || content.includes('ValueError:') || content.includes('KeyError:')) {
    const firstErrorLine = content.split('\n').find(line => line.includes('Error:'));
    if (firstErrorLine) {
      return { display: firstErrorLine.trim(), original: content };
    }
    return { display: 'An internal Python error occurred. Check details for more info.', original: content };
  }


  return { display: content, original: content };
}

export function ErrorMessage({ content, errorType, retryable, onRetry, onEditRetry }: ErrorMessageProps) {
  const [dismissed, setDismissed] = useState(false);
  const [copied, setCopied] = useState(false);
  const { display, original } = useMemo(() => parseErrorMessage(content), [content]);
  const isWarning = isWarningContent(original); // Check original content for warning patterns
  const showRetry = isEnabled('retry-ui') && retryable && onRetry;
  const showEditRetry = isEnabled('retry-ui') && onEditRetry;
  // Multi-line payloads are stringified JSON or tracebacks — set them as code.
  const isStructured = display.includes('\n');

  async function handleCopy() {
    const ok = await copyToClipboard(original);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), TIMING.copiedFeedbackMs);
    }
  }

  if (dismissed) return null;

  return (
    <div
      role={isWarning ? 'status' : 'alert'}
      className={`max-w-[min(100%,var(--measure))] rounded-[var(--radius)] border px-[var(--space-4)] py-[var(--space-3)] font-sans text-[length:var(--text-base)] ${
        isWarning
          ? 'border-[color-mix(in_oklab,var(--warn)_30%,transparent)] bg-[color-mix(in_oklab,var(--warn)_10%,transparent)] text-[var(--text)]'
          : 'border-[var(--red-border)] bg-[var(--red-bg)] text-[var(--red)]'
      }`}
    >
      <div className="flex items-start gap-[var(--space-2)]">
        {/* Severity is carried by the glyph as well as the hue — the shape
            survives monochrome and every form of colour blindness. */}
        {isWarning ? (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warn)]" aria-hidden="true" />
        ) : (
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--red)]" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <span className="sr-only">{isWarning ? 'Warning: ' : 'Error: '}</span>
          <div
            className={`whitespace-pre-wrap break-words text-[var(--text)] ${
              isStructured
                ? 'overflow-x-auto font-mono text-[length:var(--text-sm)] leading-[var(--lh-ui)]'
                : 'font-sans text-[length:var(--text-base)] leading-[var(--lh-body)]'
            }`}
          >
            {display}
          </div>
          <div className="mt-[var(--space-2)] flex flex-wrap items-center gap-[var(--space-3)] font-sans text-[length:var(--text-xs)] text-[var(--text-subtle)]">
            <button
              type="button"
              onClick={handleCopy}
              className={ACTION_BUTTON}
              aria-label={copied ? 'Error details copied to clipboard' : 'Copy error details'}
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-[var(--ok)]" aria-hidden="true" /> Copied
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" /> Copy details
                </>
              )}
            </button>
            {/* Announced separately so the label swap is not the only signal. */}
            <span role="status" className="sr-only">
              {copied ? 'Error details copied to clipboard' : ''}
            </span>
            {showRetry && (
              <button type="button" onClick={onRetry} className={ACTION_BUTTON}>
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
              </button>
            )}
            {showEditRetry && (
              <button type="button" onClick={onEditRetry} className={ACTION_BUTTON}>
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit & Retry
              </button>
            )}
            {isWarning && (
              <button type="button" onClick={() => setDismissed(true)} className={ACTION_BUTTON}>
                <X className="h-3.5 w-3.5" aria-hidden="true" /> Dismiss
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
