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
 * Sections are separated by --section-y whitespace alone — no rule between
 * them, and no label above the heading. A line reads as a wall between
 * unrelated blocks, and a label repeats what the heading already says; the
 * heading is what says "new part."
 */
export function Section({
  id,
  tone,
  children,
}: {
  id?: string;
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
  const inner = (
    <section
      id={id}
      className="mx-auto w-full max-w-[var(--width-wide)] scroll-mt-[var(--space-20)] px-[var(--gutter)] py-[var(--section-y)]"
    >
      <div className="min-w-0">{children}</div>
    </section>
  );

  if (tone !== 'invert') return inner;

  return (
    <div className="invert-band bg-[var(--bg)] text-[var(--text)]">{inner}</div>
  );
}

export function Heading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-serif text-[length:var(--text-2xl)] sm:text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
      {children}
    </h2>
  );
}

export function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-6)] text-[length:var(--text-2xl)] leading-[var(--lh-body)] text-[var(--text-2)]">
      {children}
    </p>
  );
}

export function Body({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-4)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/** A cross-reference into the record or the docs. Never a second primary CTA. */
export function Aside({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="link-smooth mt-[var(--space-6)] inline-flex font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--accent)] hover:text-[var(--accent-hover)]"
    >
      {children}
    </Link>
  );
}
