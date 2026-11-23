import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { DocMarkdown, docAnchor } from '@/components/docs/DocMarkdown';
import { DocsSidebar } from '@/components/docs/DocsSidebar';
import { JsonLd } from '@/components/seo/JsonLd';
import { CAP, FIGURE, ROW } from '@/components/site/ArgumentSection';
import { DOCS, docNeighbours, getDoc } from '@/lib/docs';
import { breadcrumbSchema, techArticleSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

interface DocParams {
  params: Promise<{ slug: string }>;
}

export function generateStaticParams() {
  return DOCS.map((doc) => ({ slug: doc.slug }));
}

export async function generateMetadata({ params }: DocParams): Promise<Metadata> {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) return { title: 'Not found' };

  const url = absoluteUrl(`/docs/${doc.slug}`);
  return {
    title: doc.title,
    description: doc.description,
    keywords: doc.keywords,
    alternates: { canonical: url },
    openGraph: {
      title: `${doc.title} — ${SITE.name} docs`,
      description: doc.description,
      url,
      type: 'article',
    },
    twitter: {
      card: 'summary_large_image',
      title: `${doc.title} — ${SITE.name} docs`,
      description: doc.description,
    },
  };
}

/** The guide's sections as anchor links: beside the text on wide screens, above it otherwise. */
function OnThisPage({ sections, id }: { sections: string[]; id: string }) {
  if (sections.length < 2) return null;
  return (
    <nav aria-labelledby={id} data-ui data-reveal className={FIGURE}>
      <p id={id} className={CAP}>
        On this page
      </p>
      <ol className="list-none">
        {sections.map((s, i) => (
          <li key={s} className={`flex items-baseline justify-between gap-[var(--space-3)] ${ROW}`}>
            <a href={`#${docAnchor(s)}`} className="site-link text-current">
              {s}
            </a>
            <span aria-hidden="true" className="nums-tabular text-[var(--site-muted)]">
              {i + 1}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * One guide in the site world "The product performs": a reading page, with
 * the guide list beside it on wide screens and the neighbouring guides at
 * its foot on every screen.
 */
export default async function DocPage({ params }: DocParams) {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) notFound();

  const { prev, next } = docNeighbours(doc.slug);
  // The guide's own h2s; DocMarkdown gives each the matching docAnchor id.
  const sections = (doc.body.match(/^## .+$/gm) ?? []).map((h) => h.slice(3));

  return (
    <>
      <JsonLd
        data={[
          techArticleSchema(doc),
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'Documentation', path: '/docs' },
            { name: doc.title, path: `/docs/${doc.slug}` },
          ]),
        ]}
      />
      <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] pb-[var(--space-24)] pt-[var(--space-32)] lg:grid-cols-12">
        <aside aria-label="Guides" className="hidden lg:col-span-3 lg:block">
          <div className="sticky top-[var(--site-sticky-top)]">
            <DocsSidebar activeSlug={doc.slug} />
          </div>
        </aside>

        <main id="main-content" className="min-w-0 lg:col-span-9 xl:col-span-6">
          <nav aria-label="Breadcrumb" className="text-[length:var(--site-small)] text-[var(--site-muted)]">
            <Link href="/docs" className="site-link text-current">
              Docs
            </Link>
            <span className="mx-[var(--space-2)]" aria-hidden="true">
              /
            </span>
            <span>{doc.section}</span>
          </nav>

          <article>
            <header className="mt-[var(--space-6)] pb-[var(--space-6)]">
              <h1 className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">
                <span className="site-line">
                  <span>{doc.title}</span>
                </span>
              </h1>
              <div className="site-after-headline">
                <p className="mt-[var(--space-6)] max-w-[52ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                  {doc.description}
                </p>
                <p className="mt-[var(--space-4)] text-[length:var(--site-small)] text-[var(--site-muted)]">
                  {doc.minutes} min read
                </p>
              </div>
            </header>

            <div className="my-[var(--space-8)] xl:hidden">
              <OnThisPage sections={sections} id="on-this-page-inline" />
            </div>

            <DocMarkdown>{doc.body}</DocMarkdown>
          </article>

          {(prev || next) && (
            <nav
              aria-label="Neighbouring guides"
              className="mt-[var(--space-16)] grid gap-[var(--space-6)] sm:grid-cols-2"
            >
              {prev ? (
                <Link href={`/docs/${prev.slug}`} className="group block">
                  <span className="block text-[length:var(--site-small)] text-[var(--site-muted)]">Previous</span>
                  <span className="site-link mt-[var(--space-1)] inline-block font-semibold text-current">{prev.title}</span>
                </Link>
              ) : (
                <span />
              )}
              {next && (
                <Link href={`/docs/${next.slug}`} className="group block sm:text-right">
                  <span className="block text-[length:var(--site-small)] text-[var(--site-muted)]">Next</span>
                  <span className="site-link mt-[var(--space-1)] inline-block font-semibold text-current">{next.title}</span>
                </Link>
              )}
            </nav>
          )}
        </main>

        <aside aria-label="On this page" className="hidden xl:col-span-3 xl:block">
          <div className="sticky top-[var(--site-sticky-top)]">
            <OnThisPage sections={sections} id="on-this-page" />
          </div>
        </aside>
      </div>
    </>
  );
}
