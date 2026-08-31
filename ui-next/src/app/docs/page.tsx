import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { DocsSidebar } from '@/components/docs/DocsSidebar';
import { JsonLd } from '@/components/seo/JsonLd';
import { DOCS, docsBySection } from '@/lib/docs';
import { breadcrumbSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Documentation',
  description:
    'Reasoner documentation: quickstart, the 19 reasoning methods, presets and model routing, credits, API keys, and the REST and streaming API reference.',
  alternates: { canonical: absoluteUrl('/docs') },
  openGraph: {
    title: `Documentation — ${SITE.name}`,
    description:
      'Quickstart, reasoning methods, presets, credits, API keys, and the full API reference.',
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

export default function DocsIndexPage() {
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
      <div className="mx-auto grid max-w-[var(--width-wide)] gap-[var(--space-12)] px-[var(--gutter)] py-[var(--space-16)] lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden lg:block">
          <div className="sticky top-24">
            <DocsSidebar />
          </div>
        </aside>

        <main id="main-content">
          <h1 className="font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">Documentation</h1>
          <p className="prose-measure mt-[var(--space-3)] max-w-2xl text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
            Everything needed to run Reasoner well — from a first query to metered
            production usage over the API.
          </p>

          <Link
            href="/docs/quickstart"
            className="mt-8 inline-flex h-11 items-center gap-2 rounded-lg bg-[var(--accent)] px-5 text-[length:var(--text-sm)] font-semibold text-[var(--accent-text)] transition-all duration-[var(--dur-micro)] hover:bg-[var(--accent-hover)] active:scale-[0.98]"
          >
            Start with the quickstart
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>

          <div className="mt-14 space-y-12">
            {docsBySection().map(({ section, pages }) => (
              <section key={section} aria-labelledby={`section-${section.replace(/\s+/g, '-')}`}>
                <h2
                  id={`section-${section.replace(/\s+/g, '-')}`}
                  className="mb-4 text-[length:var(--text-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]"
                >
                  {section}
                </h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  {pages.map((page) => (
                    <Link
                      key={page.slug}
                      href={`/docs/${page.slug}`}
                      className="group flex flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 transition-colors hover:border-[var(--accent)]"
                    >
                      <h3 className="text-[length:var(--text-base)] font-semibold text-[var(--text)] transition-colors group-hover:text-[var(--accent)]">
                        {page.title}
                      </h3>
                      <p className="mt-2 flex-1 text-[length:var(--text-sm)] leading-relaxed text-[var(--text-2)]">
                        {page.description}
                      </p>
                      <span className="mt-4 text-[length:var(--text-xs)] text-[var(--text-muted)]">
                        {page.minutes} min read
                      </span>
                    </Link>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </main>
      </div>
    </>
  );
}
