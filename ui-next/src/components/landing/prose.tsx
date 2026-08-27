import Link from 'next/link';
import type { ReactNode } from 'react';

/**
 * The editorial chrome shared by the marketing pages that are set as one
 * document: the home page and /capabilities.
 *
 * It lives apart from either of them because both use it, and because a
 * divergence between the two — a different measure, a different marker
 * column — would read as two sites rather than as one argument split across
 * two URLs.
 */

/**
 * Shares the run record's marginal-label idiom so the pages read as one
 * document. Sections are separated by the §n marker and --section-y
 * whitespace alone — no rule between them. A line reads as a wall between
 * unrelated blocks; a page of these is one argument in parts, and the
 * marker's number is what says "new part," not a border.
 */
export function Section({
  id,
  marker,
  name,
  tone,
  children,
}: {
  id?: string;
  /**
   * Omit both to drop the marginal column and run the content across the
   * full measure. The band does that: it is already set apart by its own
   * ground, so a marker labelling it is the second device doing the first
   * device's job, and the four stages would rather have the 9rem.
   */
  marker?: string;
  name?: string;
  /**
   * `invert` runs the section against the page's ground, dark on the ivory
   * theme and ivory on the dark one, and takes it full-bleed. A band that
   * stops at the 72rem measure reads as a card rather than as a change of
   * ground. The inversion is a token swap in globals.css; nothing inside a
   * section needs to know which ground it is standing on.
   */
  tone?: 'invert';
  children: ReactNode;
}) {
  const labelled = marker !== undefined || name !== undefined;

  const inner = (
    <section
      id={id}
      className="mx-auto w-full max-w-[var(--width-wide)] scroll-mt-[var(--space-20)] px-[var(--gutter)] py-[var(--section-y)]"
    >
      <div
        className={
          labelled
            ? 'grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]'
            : ''
        }
      >
        {labelled ? (
          /* Parks alongside the section it labels, so the marker stays
             visible for as long as the section it names is. */
          <div className="lg:sticky lg:top-[var(--space-24)] lg:self-start">
            {marker ? (
              <p className="nums-tabular font-mono text-[8pt] text-[var(--accent)]">{marker}</p>
            ) : null}
            <p className="mt-[var(--space-1)] font-sans text-[8pt] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
              {name}
            </p>
          </div>
        ) : null}
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );

  if (tone !== 'invert') return inner;

  return (
    <div className="scroll-grow invert-band bg-[var(--bg)] text-[var(--text)]">{inner}</div>
  );
}

export function Heading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-serif text-[21pt] sm:text-[34pt] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
      {children}
    </h2>
  );
}

export function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-6)] font-serif text-[21pt] leading-[var(--lh-body)] text-[var(--text-2)]">
      {children}
    </p>
  );
}

export function Body({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-4)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/** A cross-reference into the record or the docs. Never a second primary CTA. */
export function Aside({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="link-smooth mt-[var(--space-6)] inline-flex font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--accent)] hover:text-[var(--accent-hover)]"
    >
      {children}
    </Link>
  );
}
