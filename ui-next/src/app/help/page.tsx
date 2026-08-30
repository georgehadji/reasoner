import type { Metadata } from 'next';
import Link from 'next/link';
import { BookOpen, Key, Zap, Shield, CreditCard, LifeBuoy } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { JsonLd } from '@/components/seo/JsonLd';
import { breadcrumbSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Help Center',
  description:
    'Reasoner help center: quickstart guides, reasoning method explanations, credits and billing, API keys, security, and troubleshooting.',
  alternates: { canonical: absoluteUrl('/help') },
  openGraph: {
    title: `Help Center — ${SITE.name}`,
    description: 'Guides, API reference, billing, and troubleshooting for Reasoner.',
    url: absoluteUrl('/help'),
    type: 'website',
  },
};

const TOPICS = [
  {
    href: '/docs/quickstart',
    icon: BookOpen,
    title: 'Getting started',
    body: 'Run your first pipeline, understand the six phases, and read the VERIFIED / HYPOTHESIS / UNKNOWN labels.',
  },
  {
    href: '/docs/reasoning-methods',
    icon: Zap,
    title: 'Reasoning methods',
    body: 'All 19 methods — debate, jury, Bayesian, chain-of-verification and more — and which problem shape each one suits.',
  },
  {
    href: '/docs/presets-and-models',
    icon: Zap,
    title: 'Presets and models',
    body: 'What Budget and Premium change, how cross-lab routing works, and why fallbacks never collapse to one vendor.',
  },
  {
    href: '/docs/credits',
    icon: CreditCard,
    title: 'Credits and billing',
    body: 'What a credit is worth, when you are charged, monthly allowances, and how to read your ledger.',
  },
  {
    href: '/docs/api-keys',
    icon: Key,
    title: 'API keys',
    body: 'Create, scope, rotate, and revoke keys, and authenticate programmatic requests safely.',
  },
  {
    href: '/docs/security-and-privacy',
    icon: Shield,
    title: 'Security and privacy',
    body: 'Prompt-injection defence, retention controls, encryption, and GDPR export and deletion.',
  },
] as const;

export default function HelpPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <JsonLd
        data={breadcrumbSchema([
          { name: 'Home', path: '/' },
          { name: 'Help Center', path: '/help' },
        ])}
      />
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Masthead ───────────────────────────────────────────
            Same marginal-marker idiom as /about, /capabilities,
            /pricing, /security and /faq. */}
        <header className="mx-auto w-full max-w-[var(--width-content)] px-[var(--gutter)] pb-[var(--space-12)] pt-[var(--space-48)]">
          <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div>
              <p className="mt-[var(--space-1)] font-sans text-[length:var(--text-xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
                Help
              </p>
            </div>
            <div className="min-w-0">
              <h1 className="font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Help center.
              </h1>
              <p className="prose-measure mt-[var(--space-6)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                Guides for getting the most out of Reasoner. For the full reference, see the{' '}
                <Link href="/docs" className="font-medium text-[var(--accent)] hover:underline">
                  documentation
                </Link>
                .
              </p>
            </div>
          </div>
        </header>

        <div className="mx-auto w-full max-w-[var(--width-content)] px-[var(--gutter)] pb-[var(--space-24)]">
        <div className="grid gap-6 md:grid-cols-2">
          {TOPICS.map(({ href, icon: Icon, title, body }) => (
            <Link
              key={href}
              href={href}
              className="group flex flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 transition-colors hover:border-[var(--accent)]"
            >
              <Icon className="mb-4 h-8 w-8 text-[var(--accent)]" aria-hidden="true" />
              <h2 className="mb-2 text-xl font-bold transition-colors group-hover:text-[var(--accent)]">
                {title}
              </h2>
              <p className="text-sm leading-relaxed text-[var(--text-2)]">{body}</p>
            </Link>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <LifeBuoy className="mt-0.5 h-6 w-6 shrink-0 text-[var(--accent)]" aria-hidden="true" />
            <div>
              <h2 className="font-semibold">Still stuck?</h2>
              <p className="text-sm text-[var(--text-2)]">
                Check{' '}
                <Link href="/docs/troubleshooting" className="text-[var(--accent)] hover:underline">
                  troubleshooting
                </Link>{' '}
                and the{' '}
                <Link href="/faq" className="text-[var(--accent)] hover:underline">
                  FAQ
                </Link>
                , then get in touch.
              </p>
            </div>
          </div>
          <Link
            href="/contact"
            className="inline-flex h-10 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] px-5 text-sm font-semibold text-[var(--accent-text)] transition-colors hover:bg-[var(--accent-hover)]"
          >
            Contact support
          </Link>
        </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
