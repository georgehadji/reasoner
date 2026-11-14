import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { ArgumentSection as Section, BODY, CAP, FIGURE, HEAD, ROW } from '@/components/site/ArgumentSection';
import { CHANGELOG, type ChangelogEntry } from '@/lib/changelog';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Changelog',
  description: 'What shipped and when. Every entry names the commit on main it shipped in.',
  alternates: { canonical: absoluteUrl('/changelog') },
  openGraph: {
    title: `Changelog — ${SITE.name}`,
    description: 'What shipped and when.',
    url: absoluteUrl('/changelog'),
    type: 'website',
  },
};

/**
 * /changelog in the site world "The product performs": one section per
 * month, generated from CHANGELOG, so a new entry needs no new markup.
 */

function utc(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

/** "Nov 13" */
function shortDate(iso: string): string {
  return utc(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** "November 13, 2026" */
function longDate(iso: string): string {
  return utc(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

/** Entries grouped by month, newest first, keeping CHANGELOG's order. */
function byMonth(entries: readonly ChangelogEntry[]) {
  const months = new Map<string, ChangelogEntry[]>();
  for (const e of entries) {
    const key = e.date.slice(0, 7);
    months.set(key, [...(months.get(key) ?? []), e]);
  }
  return [...months].map(([key, items]) => ({
    key,
    label: utc(`${key}-01`).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' }),
    items,
  }));
}

/** At most five entries per fragment, so none runs past a phone screen and a half. */
function chunks(items: ChangelogEntry[], size = 5): ChangelogEntry[][] {
  return Array.from({ length: Math.ceil(items.length / size) }, (_, i) => items.slice(i * size, i * size + size));
}

function range(part: ChangelogEntry[]): string {
  const first = shortDate(part[0].date);
  const last = shortDate(part[part.length - 1].date);
  return first === last ? first : `${first} to ${last}`;
}

/** `heading`: false in the hero, where an h3 would sit under the h1 with no h2 between. */
function Entry({ entry, heading = true }: { entry: ChangelogEntry; heading?: boolean }) {
  const Title = heading ? 'h3' : 'p';
  return (
    <li className={ROW}>
      <p className="flex flex-wrap items-baseline justify-between gap-x-[var(--space-3)] text-[var(--site-muted)]">
        <time dateTime={entry.date}>{shortDate(entry.date)}</time>
        <code className="font-mono">{entry.commit}</code>
      </p>
      <Title className="mt-[var(--space-1)] font-semibold">{entry.title}</Title>
      <p className="mt-[var(--space-1)] max-w-[60ch]">{entry.description}</p>
    </li>
  );
}

export default function ChangelogPage() {
  const [latest] = CHANGELOG;
  // The hero shows the latest entry; with none there is no page to render.
  if (!latest) notFound();
  const months = byMonth(CHANGELOG);

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), the latest entry (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>What shipped,</span>
              </span>
              <span className="site-line">
                <span>and when.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Each entry names the commit it shipped in. Only work merged to main is listed; nothing planned
                or in progress.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <a href={`#m-${months[0].key}`} className="site-button">
                  Read the latest changes
                </a>
                <Link href="/status" className={`site-link ${BODY}`}>
                  See what is running now
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>Latest, {longDate(latest.date)}</figcaption>
              <ul className="list-none">
                <Entry entry={latest} heading={false} />
              </ul>
            </figure>
          </div>
        </header>

        {months.map(({ key, label, items }, i) => (
          <Section
            key={key}
            id={`m-${key}`}
            lines={[label, `${items.length} ${items.length === 1 ? 'change' : 'changes'}.`]}
            field={i % 2 === 1}
          >
            <div className="flex flex-col gap-[var(--space-6)]">
              {chunks(items).map((part) => (
                <figure key={part[0].commit} data-ui className={FIGURE}>
                  <figcaption className={CAP}>{range(part)}</figcaption>
                  <ul className="list-none">
                    {part.map((entry) => (
                      <Entry key={entry.commit} entry={entry} />
                    ))}
                  </ul>
                </figure>
              ))}
            </div>
          </Section>
        ))}

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Something changed</span>
            <span className="block">that is not here?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            Tell us what you noticed. If it shipped without an entry, the list is wrong and we will add it.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/contact" className="site-button">
              Get in touch
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
