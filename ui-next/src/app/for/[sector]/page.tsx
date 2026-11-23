import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { HeroRecord } from '@/components/site/HeroRecord';
import { PrintButton } from '@/components/site/PrintButton';
import { STATUS_RULE, StatusBands } from '@/components/site/StatusBands';
import { PROVIDERS } from '@/lib/capabilities.generated';
import { METHOD_HINTS_DATA } from '@/lib/method-hints';
import { REVIEW_STATUS_LABEL, SECTORS, getSector, type ReviewStatus } from '@/lib/sectors';
import { absoluteUrl } from '@/lib/site';

/**
 * /for/[sector] in the site world "The product performs" (spec/art-direction.md).
 * Order: the sector and its reviewer's gating question, beside the review
 * sheet as a printable fragment → every answer, banded with its status →
 * what a run gives the reviewer (the captured run record) → the pilot and
 * its methods → the other sectors.
 *
 * Every fact comes from lib/sectors.ts, where unconfirmed answers carry an
 * [INPUT REQUIRED] note rather than a guess.
 */

interface SectorParams {
  params: Promise<{ sector: string }>;
}

export function generateStaticParams() {
  return SECTORS.map(({ slug }) => ({ sector: slug }));
}

export async function generateMetadata({ params }: SectorParams): Promise<Metadata> {
  const sector = getSector((await params).sector);
  if (!sector) return { title: 'Not found' };
  return {
    title: `${sector.name}: ${sector.gate}`,
    description: `${sector.use} ${sector.limit}`,
    alternates: { canonical: absoluteUrl(`/for/${sector.slug}`) },
  };
}

/** The sector name over two lines, split where the halves are closest in length. */
function twoLines(name: string): [string, string] {
  const words = name.split(' ');
  let best = 1;
  for (let i = 1; i < words.length; i++) {
    const gap = (s: number) => Math.abs(words.slice(0, s).join(' ').length - words.slice(s).join(' ').length);
    if (gap(i) < gap(best)) best = i;
  }
  return [words.slice(0, best).join(' '), words.slice(best).join(' ')];
}

const STATUSES: ReviewStatus[] = ['available', 'to-confirm', 'not-available'];
const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';

export default async function SectorPage({ params }: SectorParams) {
  const sector = getSector((await params).sector);
  if (!sector) notFound();
  const others = SECTORS.filter((s) => s.slug !== sector.slug);
  const [first, second] = twoLines(sector.name);
  const tally = STATUSES.map((s) => [s, sector.review.filter((r) => r.status === s).length] as const).filter(([, n]) => n);

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: the sector and its question (left), the review sheet (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <nav aria-label="Breadcrumb" className="mb-[var(--space-6)] text-[var(--site-muted)]">
              <Link href="/#sectors" className="site-link">
                Sectors
              </Link>
              <span aria-hidden="true"> / </span>
              <span aria-current="page">{sector.name}</span>
            </nav>
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>{first}</span>
              </span>
              <span className="site-line">
                <span>{second}</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[36ch] font-semibold text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                {sector.gate}
              </p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>{sector.use}</p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>{sector.limit}</p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/contact?topic=pilot" className="site-button">
                  Scope a pilot
                </Link>
                <a href="#review" className={`site-link ${BODY}`}>
                  Read every answer
                </a>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <div className="flex items-center justify-between gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
                <span className="font-semibold">Review sheet</span>
                <span className="text-[var(--site-muted)] nums-tabular">{sector.review.length} questions</span>
              </div>
              <ol className="list-none">
                {sector.review.map(({ question, status }, i) => (
                  <li key={question} className="border-b border-[var(--site-line)]">
                    <a
                      href={`#q-${i}`}
                      className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-[var(--space-3)] px-[var(--space-4)] py-[var(--space-3)] hover:bg-[var(--site-surface)]"
                    >
                      <span>{question}</span>
                      <span className={`${STATUS_RULE[status]} whitespace-nowrap pl-[var(--space-2)] font-semibold`}>
                        {REVIEW_STATUS_LABEL[status]}
                      </span>
                    </a>
                  </li>
                ))}
              </ol>
              <figcaption className="flex flex-wrap items-center justify-between gap-[var(--space-3)] px-[var(--space-4)] py-[var(--space-3)]">
                <span className="text-[var(--site-muted)]">
                  {tally.map(([s, n]) => `${n} ${REVIEW_STATUS_LABEL[s].toLowerCase()}`).join(' · ')}
                </span>
                <PrintButton className="rounded-[var(--radius)] border border-[var(--site-line)] px-[var(--space-3)] py-[var(--space-1)] font-semibold hover:bg-[var(--site-surface)]">
                  Print this sheet
                </PrintButton>
              </figcaption>
            </figure>
          </div>
        </header>

        {/* ── Every answer, banded with its status ── */}
        <section
          id="review"
          aria-labelledby="review-h"
          className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]"
        >
          <div className="grid gap-[var(--space-10)] lg:grid-cols-12">
            <div className="lg:col-span-4">
              <h2 id="review-h" className={HEAD}>
                <span className="block">The reviewer&rsquo;s</span>
                <span className="block">questions.</span>
              </h2>
              <p className={`mt-[var(--space-6)] max-w-[36ch] ${BODY}`}>
                Each answer is what holds today. Where something is not confirmed, it says so rather
                than leave a gap for you to fill in. No accuracy, safety or compliance certification is
                claimed.
              </p>
            </div>
            <div className="lg:col-span-8">
              <StatusBands
                items={sector.review.map(({ question, status, answer, href }) => ({
                  title: question,
                  status,
                  detail: (
                    <>
                      {answer}
                      {href && (
                        <>
                          {' '}
                          <Link href={href} className="site-link">
                            Detail<span className="sr-only">: {question}</span>
                          </Link>
                        </>
                      )}
                    </>
                  ),
                }))}
              />
            </div>
          </div>

          {/* Anchors for the hero sheet's rows, in the same order. */}
          <div aria-hidden="true">
            {sector.review.map((r, i) => (
              <span key={r.question} id={`q-${i}`} />
            ))}
          </div>

          <div className="mt-[var(--space-16)] grid gap-[var(--space-10)] lg:grid-cols-12 lg:items-center">
            <p className={`max-w-[44ch] lg:col-span-5 ${BODY}`}>
              Every company a request can reach is listed on{' '}
              <Link href="/subprocessors" className="site-link">
                sub-processors
              </Link>
              ; every control, with its status, on{' '}
              <Link href="/security" className="site-link">
                security
              </Link>
              .
            </p>
            <figure
              data-ui
              data-reveal
              className="flex min-h-[var(--site-fragment-min-h)] w-full min-w-0 flex-col rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
            >
              <figcaption className={CAP}>Model providers a request can reach</figcaption>
              <ul className="flex flex-1 list-none flex-wrap content-start gap-[var(--space-2)] p-[var(--space-4)]">
                {PROVIDERS.map((name) => (
                  <li key={name} className="rounded-[var(--radius)] border border-[var(--site-line)] px-[var(--space-3)] py-[var(--space-1)]">
                    {name}
                  </li>
                ))}
              </ul>
              <p className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
                {sector.westernOnly
                  ? 'This sector runs Western-only: US and EU labs, and any other model is refused.'
                  : 'Turn on Western-only to keep a request to US and EU labs.'}
              </p>
            </figure>
          </div>
        </section>

        {/* ── What a run gives the reviewer: light field ── */}
        <section id="record" aria-labelledby="record-h" className="bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center">
            <div data-reveal className="order-last flex lg:order-none lg:col-span-6">
              <HeroRecord />
            </div>
            <div className="lg:col-span-5 lg:col-start-8">
              <h2 id="record-h" className={HEAD}>
                <span className="block">The record</span>
                <span className="block">comes with it.</span>
              </h2>
              <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
                Each run is stored as a log of events: every phase, which model wrote it, what the
                critic scored, and a verified, hypothesis or unknown label on each claim. These are
                claims from one captured run; switch the record off to see the answer alone.
              </p>
            </div>
          </div>
        </section>

        {/* ── The pilot and its methods ── */}
        <section
          id="fit"
          aria-labelledby="fit-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <div className="lg:col-span-5">
            <h2 id="fit-h" className={HEAD}>
              <span className="block">Start with one</span>
              <span className="block">problem.</span>
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              Pick one your team already reviews by hand. A paid pilot runs four to six weeks on it
              and is judged against your own team&rsquo;s analysis of the same problem.
            </p>
            <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
              <Link href="/contact?topic=pilot" className="site-button">
                Scope a pilot
              </Link>
              <Link href="/how-it-works" className={`site-link ${BODY}`}>
                Read a complete run
              </Link>
            </div>
          </div>

          <figure
            data-ui
            data-reveal
            className="min-h-[var(--site-fragment-min-h)] w-full min-w-0 self-end rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
          >
            <figcaption className={CAP}>Methods these questions tend to get</figcaption>
            <dl className="list-none">
              {sector.methods.map(({ name, hint }) => (
                <div key={name} className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] last:border-b-0">
                  <dt className="font-semibold">{name}</dt>
                  {hint && <dd className="mt-[var(--space-1)] text-[var(--site-muted)]">{METHOD_HINTS_DATA[hint].desc}</dd>}
                </div>
              ))}
            </dl>
          </figure>
        </section>

        {/* ── Other sectors ── */}
        <section
          id="other-sectors"
          aria-labelledby="other-h"
          className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] pb-[var(--space-24)]"
        >
          <h2 id="other-h" className={HEAD}>
            Other sectors.
          </h2>
          <ul className="mt-[var(--space-10)] grid list-none gap-x-[var(--space-10)] gap-y-[var(--space-8)] sm:grid-cols-2 lg:grid-cols-3">
            {others.map(({ slug, name, gate }) => (
              <li key={slug}>
                <Link href={`/for/${slug}`} className="group block">
                  <span className="font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)] group-hover:underline">
                    {name}
                  </span>
                  <span className={`mt-[var(--space-2)] block text-[var(--site-muted)] ${BODY}`}>{gate}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
