import type { Metadata } from 'next';
import Link from 'next/link';
import { JsonLd } from '@/components/seo/JsonLd';
import { ArgumentSection as Section, BODY, CAP, FIGURE, ROW } from '@/components/site/ArgumentSection';
import { DOCS, docsBySection, getDoc } from '@/lib/docs';
import { breadcrumbSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Documentation',
  description:
    'Reasoner documentation: a quickstart, the reasoning methods, presets and model routing, credits, API keys, MCP, and the REST and streaming API reference.',
  alternates: { canonical: absoluteUrl('/docs') },
  openGraph: {
    title: `Documentation — ${SITE.name}`,
    description: 'Quickstart, reasoning methods, presets, credits, API keys, MCP, and the full API reference.',
    url: absoluteUrl('/docs'),
    type: 'website',
  },
};

const collectionSchema = {
  '@context': 'https://schema.org',
  '@type': 'CollectionPage',
  name: `${SITE.name} documentation`,
  url: absoluteUrl('/docs'),
  description: metadata.description as string,
  hasPart: DOCS.map((doc) => ({
    '@type': 'TechArticle',
    headline: doc.title,
    description: doc.description,
    url: absoluteUrl(`/docs/${doc.slug}`),
  })),
};

/**
 * /docs in the site world "The product performs": every guide, one section
 * per DocSection, generated from DOCS so a new guide needs no new markup.
 */

/** The quickstart's own steps, read from its headings. */
const QUICKSTART_STEPS = (getDoc('quickstart')?.body.match(/^## .+$/gm) ?? []).map((h) => h.slice(3));

export default function DocsIndexPage() {
  const sections = docsBySection().filter(({ pages }) => pages.length > 0);
  return (
    <>
      <JsonLd
        data={[
          collectionSchema,
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'Documentation', path: '/docs' },
          ]),
        ]}
      />
      <main id="main-content">
        {/* ── Hero: the claim (left), the quickstart's steps (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Every guide,</span>
              </span>
              <span className="site-line">
                <span>in full.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                {DOCS.length} guides, from a first run to metered use over the API and MCP. Each is plain
                text in the page, readable without JavaScript.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/docs/quickstart" className="site-button">
                  Start with the quickstart
                </Link>
                <Link href="/help" className={`site-link ${BODY}`}>
                  Something failed?
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>The quickstart, step by step</figcaption>
              <ol className="list-none">
                {QUICKSTART_STEPS.map((step, i) => (
                  <li key={step} className={`grid grid-cols-[auto_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold nums-tabular">{i + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </figure>
          </div>
        </header>

        {sections.map(({ section, pages }, i) => (
          <Section
            key={section}
            id={section.toLowerCase().replace(/\s+/g, '-')}
            lines={[section, `${pages.length} ${pages.length === 1 ? 'guide' : 'guides'}.`]}
            field={i % 2 === 1}
          >
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>{section}</figcaption>
              <ul className="list-none">
                {pages.map((page) => (
                  <li key={page.slug} className={ROW}>
                    <p className="flex flex-wrap items-baseline justify-between gap-x-[var(--space-3)]">
                      <Link href={`/docs/${page.slug}`} className="site-link font-semibold text-current">
                        {page.title}
                      </Link>
                      <span className="text-[var(--site-muted)]">{page.minutes} min</span>
                    </p>
                    <p className="mt-[var(--space-1)]">{page.description}</p>
                  </li>
                ))}
              </ul>
            </figure>
          </Section>
        ))}
      </main>
    </>
  );
}
