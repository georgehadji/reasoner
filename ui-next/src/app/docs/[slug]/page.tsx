import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { DocMarkdown } from '@/components/docs/DocMarkdown';
import { DocsSidebar } from '@/components/docs/DocsSidebar';
import { JsonLd } from '@/components/seo/JsonLd';
import { DOCS, docNeighbours, getDoc } from '@/lib/docs';
import { breadcrumbSchema, techArticleSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

interface DocParams {
  params: Promise<{ slug: string }>;
}

/** Pre-renders every doc at build time — no client fetch, no empty shell. */
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

export default async function DocPage({ params }: DocParams) {
  const { slug } = await params;
  const doc = getDoc(slug);
  if (!doc) notFound();

  const { prev, next } = docNeighbours(doc.slug);

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
      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-16 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden lg:block">
          <div className="sticky top-24">
            <DocsSidebar activeSlug={doc.slug} />
          </div>
        </aside>

        <main id="main-content" className="min-w-0 max-w-3xl">
          <nav aria-label="Breadcrumb" className="mb-6 text-sm text-[var(--text-muted)]">
            <Link href="/docs" className="transition-colors hover:text-[var(--text)]">
              Docs
            </Link>
            <span className="mx-2" aria-hidden="true">
              /
            </span>
            <span className="text-[var(--text-2)]">{doc.section}</span>
          </nav>

          <article>
            <header className="mb-10 border-b border-[var(--border)] pb-8">
              <h1 className="text-4xl font-bold tracking-tight text-[var(--text)]">{doc.title}</h1>
              <p className="mt-3 text-lg leading-relaxed text-[var(--text-muted)]">
                {doc.description}
              </p>
              <p className="mt-4 text-xs uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {doc.minutes} min read
              </p>
            </header>

            <DocMarkdown>{doc.body}</DocMarkdown>
          </article>

          {(prev || next) && (
            <nav
              aria-label="Documentation pagination"
              className="mt-16 grid gap-4 border-t border-[var(--border)] pt-8 sm:grid-cols-2"
            >
              {prev ? (
                <Link
                  href={`/docs/${prev.slug}`}
                  className="group flex flex-col rounded-xl border border-[var(--border)] p-4 transition-colors hover:border-[var(--accent)]"
                >
                  <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                    Previous
                  </span>
                  <span className="mt-1 font-medium text-[var(--text)] group-hover:text-[var(--accent)]">
                    {prev.title}
                  </span>
                </Link>
              ) : (
                <span />
              )}
              {next && (
                <Link
                  href={`/docs/${next.slug}`}
                  className="group flex flex-col rounded-xl border border-[var(--border)] p-4 text-right transition-colors hover:border-[var(--accent)] sm:col-start-2"
                >
                  <span className="flex items-center justify-end gap-1.5 text-xs text-[var(--text-muted)]">
                    Next
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </span>
                  <span className="mt-1 font-medium text-[var(--text)] group-hover:text-[var(--accent)]">
                    {next.title}
                  </span>
                </Link>
              )}
            </nav>
          )}
        </main>
      </div>
    </>
  );
}
