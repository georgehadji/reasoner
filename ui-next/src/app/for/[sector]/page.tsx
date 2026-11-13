import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import {
  Body,
  Heading,
  LABEL_TAG,
  Lede,
  PilotCta,
  SECONDARY_CTA,
  Section,
} from '@/components/landing/prose';
import { REVIEW_STATUS_LABEL, SECTORS, getSector, type ReviewStatus } from '@/lib/sectors';
import { absoluteUrl } from '@/lib/site';

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

/* The status carries three signals: the word, the rule style and the ink,
   so it survives monochrome printing (reviewers print these pages). */
const STATUS_RULE: Record<ReviewStatus, string> = {
  available: 'epistemic-verified',
  'to-confirm': 'epistemic-unknown',
  'not-available': 'border-l-2 border-[var(--text-subtle)] text-[var(--text-muted)]',
};

const INLINE_LINK =
  'link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]';

export default async function SectorPage({ params }: SectorParams) {
  const sector = getSector((await params).sector);
  if (!sector) notFound();
  const others = SECTORS.filter((s) => s.slug !== sector.slug);

  return (
    <div className="min-h-dvh bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead: the reviewer's question, asked as they would ask it ── */}
        <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-48)]">
          <nav aria-label="Breadcrumb" className="mb-[var(--space-6)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            <Link href="/#sectors" className={INLINE_LINK}>
              Sectors
            </Link>
            <span aria-hidden="true"> / </span>
            <span aria-current="page">{sector.name}</span>
          </nav>
          <h1 className="max-w-[20ch] text-balance font-display text-[length:var(--text-5xl)] font-normal leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)] lg:text-[length:var(--text-6xl)]">
            {sector.gate}
          </h1>
          <p className="prose-measure mt-[var(--space-8)] text-[length:var(--text-xl)] leading-[var(--lh-body)] text-[var(--text-2)]">
            {sector.use}
          </p>
          <p className="prose-measure mt-[var(--space-4)] text-[length:var(--text-md)] font-semibold leading-[var(--lh-body)] text-[var(--text)]">
            {sector.limit}
          </p>
          <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-3)] gap-x-[var(--space-8)]">
            <PilotCta />
            <a href="#review" className={SECONDARY_CTA}>
              Read the review sheet
            </a>
          </div>
        </header>

        {/* ── Review sheet: document mode, no plates, prints cleanly ── */}
        <Section id="review">
          <Heading>What your reviewer will ask.</Heading>
          <Lede>
            Each answer is what holds today. Where we have not confirmed something, it says so
            rather than leaving a gap for you to fill in.
          </Lede>

          <dl className="mt-[var(--space-10)] divide-y divide-[var(--border)] border-y border-[var(--border)]">
            {sector.review.map(({ question, status, answer, href }) => (
              <div
                key={question}
                className="grid gap-[var(--space-2)] py-[var(--space-6)] lg:grid-cols-[minmax(0,18rem)_minmax(0,8rem)_minmax(0,1fr)] lg:gap-[var(--space-8)]"
              >
                <dt className="font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {question}
                </dt>
                <dd className={`${STATUS_RULE[status]} ${LABEL_TAG} self-start`}>
                  {REVIEW_STATUS_LABEL[status]}
                </dd>
                <dd className="prose-measure min-w-0 text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                  {answer}
                  {href && (
                    <>
                      {' '}
                      <Link href={href} className={INLINE_LINK}>
                        Detail<span className="sr-only">: {question}</span>
                      </Link>
                    </>
                  )}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            No accuracy, safety or compliance certification is claimed. The full controls list is on{' '}
            <Link href="/security" className={INLINE_LINK}>
              security
            </Link>
            , and every provider a request can reach is on{' '}
            <Link href="/subprocessors" className={INLINE_LINK}>
              sub-processors
            </Link>
            .
          </Body>
        </Section>

        {/* ── Fit ─────────────────────────────────────────────── */}
        <Section id="fit" tone="invert">
          <Heading>Start with one problem your team already reviews by hand.</Heading>
          <Lede>
            A paid pilot runs four to six weeks on that problem and is judged against your own
            team&rsquo;s analysis of it. The methods these questions tend to get:
          </Lede>
          <p className="mt-[var(--space-6)] font-mono text-[length:var(--text-md)] leading-[var(--lh-ui)] text-[var(--text-2)]">
            {sector.methods}
          </p>
          <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-3)] gap-x-[var(--space-8)]">
            <PilotCta />
            <Link href="/how-it-works" className={SECONDARY_CTA}>
              Read a complete run
            </Link>
          </div>
        </Section>

        {/* ── Other sectors ───────────────────────────────────── */}
        <Section id="other-sectors">
          <Heading>Other sectors</Heading>
          <ul className="mt-[var(--space-8)] grid list-none gap-x-[var(--space-8)] gap-y-[var(--space-4)] sm:grid-cols-2 lg:grid-cols-3">
            {others.map(({ slug, name, gate }) => (
              <li key={slug} className="border-t border-[var(--border)] pt-[var(--space-4)]">
                <Link href={`/for/${slug}`} className={`${INLINE_LINK} font-sans text-[length:var(--text-md)] font-semibold`}>
                  {name}
                </Link>
                <p className="mt-[var(--space-1)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {gate}
                </p>
              </li>
            ))}
          </ul>
        </Section>
      </main>

      <SiteFooter />
    </div>
  );
}
