'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/error-reporting';

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  useEffect(() => {
    reportError(error, { source: 'client' });
  }, [error]);

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-[var(--bg)] p-6 text-center">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--red-bg)] text-[var(--red)]">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" x2="12" y1="8" y2="12" />
          <line x1="12" x2="12.01" y1="16" y2="16" />
        </svg>
      </div>
      <h2 className="mb-2 text-xl font-semibold text-[var(--text)]">
        Something went wrong
      </h2>
      <p className="mb-8 max-w-sm text-sm leading-relaxed text-[var(--text-2)]">
        We&apos;ve been notified and are looking into it. If this persists, try refreshing the page.
      </p>
      <button
        onClick={() => reset()}
        className="inline-flex items-center justify-center rounded-[var(--radius-lg)] bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-[var(--accent-text)] transition-all hover:opacity-90 active:scale-[0.98]"
      >
        Try again
      </button>
    </div>
  );
}
