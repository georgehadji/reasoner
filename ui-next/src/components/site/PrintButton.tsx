'use client';

/** Prints the page. Sector review sheets are printed and passed to a reviewer. */
export function PrintButton({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <button type="button" onClick={() => window.print()} className={className}>
      {children}
    </button>
  );
}
