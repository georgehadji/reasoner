import Link from 'next/link';
import type { ReactNode } from 'react';

/**
 * Chrome for the long-argument marketing pages (/capabilities, /developers)
 * in the site world "The product performs": one claim per section, each a
 * two-line heading, its argument, and optionally an interface fragment.
 */

export const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
export const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
export const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';
export const FIGURE =
  'w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-ink)]';
export const ROW = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] last:border-b-0';

/**
 * One claim. With a figure: text and fragment side by side (the fragment
 * leads on the light field). Without: the heading on the left, the argument
 * on the right.
 */
export function ArgumentSection({
  id,
  lines,
  field = false,
  figure,
  children,
}: {
  id: string;
  lines: [string, string];
  field?: boolean;
  figure?: ReactNode;
  children: ReactNode;
}) {
  const heading = (
    <h2 id={`${id}-h`} className={HEAD}>
      <span className="block">{lines[0]}</span>
      <span className="block">{lines[1]}</span>
    </h2>
  );
  return (
    <section
      id={id}
      aria-labelledby={`${id}-h`}
      className={`scroll-mt-[var(--space-20)] ${field ? 'bg-[var(--site-field)] text-[var(--site-field-ink)]' : ''}`}
    >
      <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-10)] px-[var(--site-margin)] py-[var(--space-16)] lg:grid-cols-12 lg:items-center lg:gap-[var(--space-12)] lg:py-[var(--space-24)]">
        {figure ? (
          <>
            <div className={field ? 'lg:col-span-5 lg:col-start-8 lg:row-start-1' : 'lg:col-span-5'}>
              {heading}
              {children}
            </div>
            <div
              data-reveal
              className={`flex min-w-0 ${field ? 'lg:col-span-6 lg:col-start-1 lg:row-start-1' : 'lg:col-span-6 lg:col-start-7'}`}
            >
              {figure}
            </div>
          </>
        ) : (
          <>
            <div className="self-start lg:col-span-5">{heading}</div>
            <div className="lg:col-span-6 lg:col-start-7 [&>*:first-child]:mt-0">{children}</div>
          </>
        )}
      </div>
    </section>
  );
}

export function ArgumentBody({ children }: { children: ReactNode }) {
  return <p className={`mt-[var(--space-6)] max-w-[60ch] ${BODY}`}>{children}</p>;
}

/** The link at the foot of a section, to its proof or its reference. */
export function More({ href, children }: { href: string; children: ReactNode }) {
  return (
    <p className={`mt-[var(--space-8)] ${BODY}`}>
      {/* text-current: .site-link pins the dark-ground ink, unreadable on the light field. */}
      <Link href={href} className="site-link text-current">
        {children}
      </Link>
    </p>
  );
}
