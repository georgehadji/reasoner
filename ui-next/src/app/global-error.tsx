'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/error-reporting';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportError(error, { source: 'client', url: typeof window !== 'undefined' ? window.location.href : undefined });
  }, [error]);

  return (
    <html>
      {/* global-error renders outside the root layout, so globals.css is not
          loaded and var() would resolve to nothing here. These hex literals
          are deliberate — keep them literal, mirroring the dark palette. */}
      <body className="flex min-h-[100dvh] flex-col items-center justify-center bg-[#1A1614] p-6 text-center">
        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 text-red-500">
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
        <h2 className="mb-2 text-[length:var(--text-xl)] font-semibold text-[#FAF1EC]">
          Critical Error
        </h2>
        <p className="mb-8 max-w-sm text-[length:var(--text-sm)] leading-relaxed text-[#A59B95]">
          The application failed to load. We&apos;ve been notified. Please refresh the page to try again.
        </p>
        <button
          onClick={() => reset()}
          className="inline-flex items-center justify-center rounded-xl bg-[#D4C9C3] px-5 py-2.5 text-[length:var(--text-sm)] font-semibold text-[#1A1614] transition-all hover:opacity-90 active:scale-[0.98]"
        >
          Refresh
        </button>
      </body>
    </html>
  );
}
