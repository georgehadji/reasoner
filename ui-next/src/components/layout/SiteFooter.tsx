import Link from 'next/link';
import { Logo } from '@/components/brand/Logo';
import { SecurityBadge } from './SecurityBadge';

const LINKS = {
  Product: [
    { label: 'About', href: '/about' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'Docs', href: '/help' },
  ],
  Legal: [
    { label: 'Privacy', href: '/privacy' },
    { label: 'Security', href: '/security' },
    { label: 'Terms', href: '/terms' },
    // The cookie policy existed but nothing linked to it, and the refund policy
    // is required by the guarantee advertised on the pricing page.
    { label: 'Cookies', href: '/cookies' },
    { label: 'Refunds', href: '/refunds' },
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
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-[var(--text)]">
              Advanced Reasoning Architecture — multi-method pipelines with verified, auditable outputs.
            </p>
          </div>

          {/* Links */}
          {Object.entries(LINKS).map(([group, items]) => (
            <div key={group}>
              <div className="mb-4 text-xs font-semibold uppercase tracking-widest text-[var(--text)]">
                {group}
              </div>
              <ul className="flex flex-col gap-2.5">
                {items.map(({ label, href }) => (
                  <li key={href}>
                    <Link
                      href={href}
                      className="text-sm text-[var(--text)] transition-colors duration-200 hover:text-[var(--text)]"
                    >
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-[var(--border)] pt-8 text-xs text-[var(--text-2)] sm:flex-row">
          <p>© {new Date().getFullYear()} Reasoner. All rights reserved.</p>
          <p>Built for critical decisions.</p>
        </div>
      </div>
    </footer>
  );
}
