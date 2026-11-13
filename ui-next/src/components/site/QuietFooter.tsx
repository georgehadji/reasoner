import Link from 'next/link';

/** A single quiet line instead of a footer block (spec/art-direction.md). */
const LINKS = [
  { href: '/how-it-works', label: 'How it works' },
  { href: '/security', label: 'Security' },
  { href: '/developers', label: 'Developers' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/contact', label: 'Contact' },
];

export function QuietFooter() {
  return (
    <footer className="mt-[var(--site-footer-gap-phone)] lg:mt-[var(--site-footer-gap)] grid gap-[var(--space-2)] px-[var(--site-margin)] pb-[var(--space-8)] text-[length:var(--site-small)] text-[var(--site-muted)] lg:grid-cols-[1fr_auto_1fr] lg:items-baseline">
      <p>Reasoner, a reasoning record</p>
      <nav aria-label="Footer">
        <ul className="flex list-none flex-wrap gap-x-[var(--space-6)] gap-y-[var(--space-1)]">
          {LINKS.map((l) => (
            <li key={l.href}>
              <Link href={l.href} className="text-[var(--site-ink)] hover:underline">
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <p className="lg:text-right">
        © {new Date().getFullYear()} ·{' '}
        <Link href="/privacy" className="text-[var(--site-ink)] hover:underline">
          Privacy
        </Link>
      </p>
    </footer>
  );
}
