import Link from 'next/link';
import { Logo } from '@/components/brand/Logo';
import { SITE } from '@/lib/site';
import { SecurityBadge } from './SecurityBadge';

const LINKS = {
  Product: [
    { label: 'Capabilities', href: '/capabilities' },
    { label: 'How it works', href: '/how-it-works' },
    { label: 'About', href: '/about' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'Developers', href: '/developers' },
    { label: 'Docs', href: '/docs' },
    { label: 'FAQ', href: '/faq' },
    { label: 'Changelog', href: '/changelog' },
    { label: 'Status', href: '/status' },
  ],
  Legal: [
    { label: 'Privacy', href: '/privacy' },
    { label: 'Security', href: '/security' },
    { label: 'Sub-processors', href: '/subprocessors' },
    { label: 'Terms', href: '/terms' },
    { label: 'Contact', href: '/contact' },
  ],
};

export function SiteFooter() {
  return (
    <footer className="border-t border-[var(--border)] bg-[var(--bg)]">
      <div className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-4">
          {/* Brand */}
          <div className="lg:col-span-2">
            <div className="flex items-center gap-3">
              <Logo showWordmark size={22} />
              <SecurityBadge />
            </div>
            <p className="mt-4 max-w-sm text-[length:var(--text-sm)] leading-relaxed text-[var(--text)]">
              Advanced Reasoning Architecture. Multi-method pipelines with verified, auditable
              outputs.
            </p>
          </div>

          {/* Links */}
          {Object.entries(LINKS).map(([group, items]) => (
            <div key={group}>
              <div className="mb-4 text-[length:var(--text-xs)] font-semibold uppercase tracking-widest text-[var(--text)]">
                {group}
              </div>
              <ul className="flex flex-col">
                {items.map(({ label, href }) => (
                  <li key={href}>
                    {/* 40px hit area (WCAG 2.5.5) built from padding, not a
                        visible box, so the column still reads as a tight list.
                        The old rule set hover to the same value as rest, so
                        there was no hover feedback at all. */}
                    <Link
                      href={href}
                      className="inline-flex min-h-[var(--space-10)] items-center text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--accent)]"
                    >
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-[var(--border)] pt-8 text-[length:var(--text-xs)] text-[var(--text-2)] sm:flex-row">
          <p>
            © {new Date().getFullYear()} {SITE.name}, operated by {SITE.legalName}.
          </p>
          <p>Built for critical decisions.</p>
        </div>
      </div>
    </footer>
  );
}
