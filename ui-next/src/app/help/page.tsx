import type { Metadata } from 'next';
import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { JsonLd } from '@/components/seo/JsonLd';
import { ArgumentSection as Section, BODY, CAP, FIGURE, HEAD, ROW } from '@/components/site/ArgumentSection';
import { DOCS, DOC_SECTIONS, type DocSection, getDoc } from '@/lib/docs';
import { FAQS, type FaqTopic, faqAnchor } from '@/lib/faq';
import { breadcrumbSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Help',
  description:
    'Common failures and their fixes, every guide in the documentation grouped by what you need, and the questions people ask first.',
  alternates: { canonical: absoluteUrl('/help') },
  openGraph: {
    title: `Help — ${SITE.name}`,
    description: 'Common failures, every guide, and the questions people ask first.',
    url: absoluteUrl('/help'),
    type: 'website',
  },
};

/**
 * /help in the site world "The product performs".
 *
 * Rebuilt 2026-11-14. The old page was six hand-written cards whose copy
 * had drifted from the docs it linked to: "all 19 methods", "retention
 * controls" (retention is not configurable) and key "scopes". Every list
 * here is now read from DOCS and FAQS, so the page cannot say more than the
 * guides do.
 */

/** The troubleshooting guide's own headings: the failures people hit. */
const FAILURES = (getDoc('troubleshooting')?.body.match(/^## .+$/gm) ?? []).map((h) => h.slice(3));

/** Doc sections grouped by what a reader is trying to do. */
const GROUPS: { id: string; lines: [string, string]; sections: DocSection[] }[] = [
  { id: 'start', lines: ['From a first run', 'to the right method.'], sections: ['Getting started', 'Reasoning'] },
  { id: 'make', lines: ['Images, articles', 'and code.'], sections: ['Generation'] },
  { id: 'build', lines: ['Keys, the API,', 'and what it costs.'], sections: ['Developers', 'Billing'] },
  { id: 'operate', lines: ['Your data, and', 'what can go wrong.'], sections: ['Operations'] },
];

// A section added to DOC_SECTIONS later still appears, under its own name.
const ungrouped = DOC_SECTIONS.filter((s) => !GROUPS.some((g) => g.sections.includes(s)));
const ALL_GROUPS = [
  ...GROUPS,
  ...ungrouped.map((s) => ({ id: s.toLowerCase().replace(/\s+/g, '-'), lines: [s, 'guides.'] as [string, string], sections: [s] })),
];

/** The first question on /faq for each topic. */
const FIRST_QUESTIONS = (['product', 'cost', 'code', 'data'] satisfies FaqTopic[])
  .map((topic) => FAQS.find((f) => f.topic === topic))
  .filter((f) => f !== undefined);

/** The answer's opening sentence; the full answer is one click away. */
function firstSentence(text: string): string {
  return text.match(/^.+?[.?!](?=\s|$)/)?.[0] ?? text;
}

export default function HelpPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <JsonLd
        data={breadcrumbSchema([
          { name: 'Home', path: '/' },
          { name: 'Help', path: '/help' },
        ])}
      />
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), the common failures (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>What went</span>
              </span>
              <span className="site-line">
                <span>wrong?</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                The failures people hit most, each with its fix. Then all {DOCS.length} guides, grouped by
                what you are trying to do.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/docs/troubleshooting" className="site-button">
                  Read the fixes
                </Link>
                <Link href="/contact" className={`site-link ${BODY}`}>
                  Ask a person
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>Common failures, from the troubleshooting guide</figcaption>
              <ul className="list-none">
                {FAILURES.map((failure) => (
                  <li key={failure} className={ROW}>
                    {failure}
                  </li>
                ))}
              </ul>
            </figure>
          </div>
        </header>

        {ALL_GROUPS.map(({ id, lines, sections }, i) => {
          const pages = DOCS.filter((d) => sections.includes(d.section));
          if (pages.length === 0) return null;
          return (
            <Section key={id} id={id} lines={lines} field={i % 2 === 1}>
              <figure data-ui className={FIGURE}>
                <figcaption className={CAP}>{sections.join(' and ')}</figcaption>
                <ul className="list-none">
                  {pages.map((doc) => (
                    <li key={doc.slug} className={ROW}>
                      <Link href={`/docs/${doc.slug}`} className="site-link font-semibold text-current">
                        {doc.title}
                      </Link>
                      <p className="mt-[var(--space-1)]">{doc.description}</p>
                    </li>
                  ))}
                </ul>
              </figure>
            </Section>
          );
        })}

        <Section id="faq" lines={['The questions', 'people ask first.']} field={ALL_GROUPS.length % 2 === 1}>
          <figure data-ui className={FIGURE}>
            <figcaption className={CAP}>One from each topic on the FAQ</figcaption>
            <ul className="list-none">
              {FIRST_QUESTIONS.map(({ q, a }) => (
                <li key={q} className={ROW}>
                  <Link href={`/faq#${faqAnchor(q)}`} className="site-link font-semibold text-current">
                    {q}
                  </Link>
                  <p className="mt-[var(--space-1)]">{firstSentence(a)}</p>
                </li>
              ))}
            </ul>
          </figure>
          <p className={`mt-[var(--space-8)] ${BODY}`}>
            <Link href="/faq" className="site-link text-current">
              All {FAQS.length} questions, answered in full
            </Link>
          </p>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Not in any</span>
            <span className="block">of these?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            Tell us what happened and what you expected. If the guides missed it, that is a gap we will fill.
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
