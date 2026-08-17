import type { Metadata } from 'next';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CHANGELOG } from '@/lib/changelog';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Changelog',
  description: 'What shipped and when — a dated record of Reasoner releases.',
  alternates: { canonical: absoluteUrl('/changelog') },
  openGraph: {
    title: `Changelog — ${SITE.name}`,
    description: 'What shipped and when.',
    url: absoluteUrl('/changelog'),
    type: 'website',
  },
};

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export default function ChangelogPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main className="mx-auto w-full max-w-[var(--width-content)] flex-1 px-[var(--gutter)] py-[var(--space-24)]">
        <header className="mb-[var(--space-16)]">
          <h1 className="font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)] md:text-[length:var(--text-5xl)]">
            Changelog
          </h1>
          <p className="prose-measure mt-[var(--space-4)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            What shipped and when.
          </p>
        </header>

        <ol role="list" className="space-y-[var(--space-12)] border-l border-[var(--border)] pl-[var(--space-8)]">
          {CHANGELOG.map((entry) => (
            <li key={`${entry.date}-${entry.title}`} className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[calc(var(--space-8)_+_4px)] top-[var(--space-1)] h-[var(--space-2)] w-[var(--space-2)] rounded-[var(--radius-pill)] bg-[var(--accent)]"
              />
              <time
                dateTime={entry.date}
                className="font-mono text-[length:var(--text-xs)] uppercase tracking-[var(--tracking-label)] text-[var(--text-subtle)]"
              >
                {formatDate(entry.date)}
              </time>
              <h2 className="mt-[var(--space-2)] font-serif text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
                {entry.title}
              </h2>
              <p className="prose-measure mt-[var(--space-2)] text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                {entry.description}
              </p>
            </li>
          ))}
        </ol>
      </main>

      <SiteFooter />
    </div>
  );
}
