import type { Metadata } from 'next';
import Link from 'next/link';
import { ChevronDown } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { JsonLd } from '@/components/seo/JsonLd';
import { FAQS } from '@/lib/faq';
import { breadcrumbSchema, faqSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Frequently Asked Questions',
  description:
    'Answers about Reasoner: how multi-method reasoning works, how credits and billing are metered, API access, model routing across labs, memory, and data retention.',
  alternates: { canonical: absoluteUrl('/faq') },
  openGraph: {
    title: `FAQ — ${SITE.name}`,
    description: 'How Reasoner works, what it costs, and how your data is handled.',
    url: absoluteUrl('/faq'),
    type: 'website',
  },
};

/**
 * Server component by design. The previous client accordion only rendered the
 * open answer, so nine of ten answers were absent from the HTML a crawler or
 * answer engine receives. Native <details> keeps every answer in the document
 * while staying collapsible without JavaScript.
 */
export default function FAQPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <JsonLd
        data={[
          faqSchema(FAQS),
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'FAQ', path: '/faq' },
          ]),
        ]}
      />
      <SiteHeader />
      <main id="main-content" className="mx-auto w-full max-w-3xl flex-1 px-6 py-16 pt-24">
        <h1 className="mb-2 text-4xl font-bold tracking-tight">Frequently Asked Questions</h1>
        <p className="mb-12 text-lg text-[var(--text-muted)]">
          Common questions about Reasoner. For depth, see the{' '}
          <Link href="/docs" className="font-medium text-[var(--accent)] hover:underline">
            documentation
          </Link>
          .
        </p>

        <div className="space-y-4">
          {FAQS.map((faq, idx) => (
            <details
              key={faq.q}
              open={idx === 0}
              className="group overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] transition-colors"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-2)] [&::-webkit-details-marker]:hidden">
                <h2 className="text-base font-medium">{faq.q}</h2>
                <ChevronDown
                  className="h-5 w-5 shrink-0 text-[var(--text-muted)] transition-transform duration-200 group-open:rotate-180"
                  aria-hidden="true"
                />
              </summary>
              <div className="border-t border-[var(--border)] px-5 pb-5 pt-4 text-[var(--text-2)]">
                <p className="leading-relaxed">{faq.a}</p>
              </div>
            </details>
          ))}
        </div>

        <div className="mt-12 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center">
          <p className="text-[var(--text-2)]">
            Something not covered here?{' '}
            <Link href="/contact" className="font-medium text-[var(--accent)] hover:underline">
              Get in touch
            </Link>
            .
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
