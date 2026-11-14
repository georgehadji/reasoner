import Link from 'next/link';
import { SITE } from '@/lib/site';

/**
 * A single quiet line instead of a footer block (spec/art-direction.md):
 * what this is at the left, the links in the middle in four named groups,
 * the year and the operator at the right. No logo, no columns, no rule above it. On a phone
 * the three parts stack on the left margin.
 */
const GROUPS = [
  {
    name: 'Product',
    links: [
      { label: 'Capabilities', href: '/capabilities' },
      { label: 'How it works', href: '/how-it-works' },
      { label: 'Pricing', href: '/pricing' },
    ],
  },
  {
    name: 'Build',
    links: [
      { label: 'Developers', href: '/developers' },
      { label: 'Docs', href: '/docs' },
      { label: 'Changelog', href: '/changelog' },
      { label: 'Status', href: '/status' },
    ],
  },
  {
    name: 'Trust',
    links: [
      { label: 'Security', href: '/security' },
      { label: 'Sub-processors', href: '/subprocessors' },
      { label: 'Privacy', href: '/privacy' },
      { label: 'Cookies', href: '/cookies' },
      { label: 'Terms', href: '/terms' },
    ],
  },
  {
    name: 'Company',
    links: [
      { label: 'About', href: '/about' },
      { label: 'FAQ', href: '/faq' },
      { label: 'Contact', href: '/contact' },
    ],
  },
];

const LINK =
  'inline-flex min-h-[var(--space-8)] items-center text-[var(--text)] underline-offset-4 transition-colors duration-[var(--dur-micro)] hover:underline';

export function SiteFooter() {
  return (
    <footer className="mt-[var(--space-24)] grid gap-[var(--space-2)] px-[var(--gutter)] pb-[var(--space-8)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)] lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:items-baseline lg:gap-[var(--space-8)]">
      <p className="lg:whitespace-nowrap">{SITE.name}, a reasoning record</p>
      <nav aria-label="Footer" className="flex flex-wrap gap-x-[var(--space-8)] gap-y-[var(--space-2)] lg:justify-center">
        {GROUPS.map(({ name, links }) => (
          <div key={name} className="flex flex-wrap items-baseline gap-x-[var(--space-4)]">
            <h2 id={`footer-${name}`} className="text-[length:var(--text-sm)] font-normal text-[var(--text-muted)]">
              {name}
            </h2>
            <ul aria-labelledby={`footer-${name}`} className="flex list-none flex-wrap gap-x-[var(--space-4)]">
              {links.map(({ label, href }) => (
                <li key={href}>
                  <Link href={href} className={LINK}>
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <p className="lg:whitespace-nowrap lg:text-right">
        © {new Date().getFullYear()} {SITE.name}, operated by {SITE.legalName}
      </p>
    </footer>
  );
}
