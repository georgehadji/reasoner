import type { Metadata } from 'next';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { StatusClient } from './StatusClient';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Status',
  description: 'Live operational status of the Reasoner API, checked in real time.',
  alternates: { canonical: absoluteUrl('/status') },
  openGraph: {
    title: `Status — ${SITE.name}`,
    description: 'Live operational status, checked in real time.',
    url: absoluteUrl('/status'),
    type: 'website',
  },
};

export default function StatusPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main className="mx-auto w-full max-w-[var(--width-content)] flex-1 px-[var(--gutter)] py-[var(--space-24)]">
        <header className="mb-[var(--space-16)]">
          <h1 className="font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)] md:text-[length:var(--text-5xl)]">
            Status
          </h1>
          <p className="prose-measure mt-[var(--space-4)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            Live, checked when this page loads — not a historical uptime report. We don&rsquo;t yet publish
            uptime history or run third-party monitoring; if something looks wrong, <a href="/contact" className="underline hover:text-[var(--accent)]">contact us</a>.
          </p>
        </header>

        <StatusClient />
      </main>

      <SiteFooter />
    </div>
  );
}
