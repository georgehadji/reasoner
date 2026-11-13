import Link from 'next/link';
import { SITE } from '@/lib/site';

/**
 * A single quiet line instead of a footer block (spec/art-direction.md):
 * what this is at the left, the links in the middle, the year and the
 * operator at the right. No logo, no columns, no rule above it. On a phone
 * the three parts stack on the left margin.
 */
const LINKS = [
  { label: 'Capabilities', href: '/capabilities' },
  { label: 'How it works', href: '/how-it-works' },
  { label: 'Pricing', href: '/pricing' },
  { label: 'Developers', href: '/developers' },
  { label: 'Docs', href: '/docs' },
  { label: 'FAQ', href: '/faq' },
  { label: 'About', href: '/about' },
  { label: 'Changelog', href: '/changelog' },
  { label: 'Status', href: '/status' },
  { label: 'Security', href: '/security' },
  { label: 'Sub-processors', href: '/subprocessors' },
  { label: 'Terms', href: '/terms' },
  { label: 'Privacy', href: '/privacy' },
  { label: 'Contact', href: '/contact' },
];

const LINK =
  'inline-flex min-h-[var(--space-8)] items-center text-[var(--text)] underline-offset-4 transition-colors duration-[var(--dur-micro)] hover:underline';

export function SiteFooter() {
  return (
    <footer className="mt-[var(--space-24)] grid gap-[var(--space-2)] px-[var(--gutter)] pb-[var(--space-8)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)] lg:grid-cols-[1fr_auto_1fr] lg:items-baseline lg:gap-[var(--space-8)]">
      <p>{SITE.name}, a reasoning record</p>
      <nav aria-label="Footer">
        <ul className="flex max-w-[48rem] list-none flex-wrap gap-x-[var(--space-6)] lg:justify-center">
          {LINKS.map(({ label, href }) => (
            <li key={href}>
              <Link href={href} className={LINK}>
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <p className="lg:text-right">
        © {new Date().getFullYear()} {SITE.name}, operated by {SITE.legalName}
      </p>
    </footer>
  );
}
