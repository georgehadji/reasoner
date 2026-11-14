import type { Metadata } from 'next';
import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { JsonLd } from '@/components/seo/JsonLd';
import {
  ArgumentSection as Section,
  BODY,
  CAP,
  FIGURE,
  HEAD,
  More,
  ROW,
} from '@/components/site/ArgumentSection';
import { CREDITS_PER_USD, FREE_CREDITS, RUN_COSTS, runsPerMonth } from '@/lib/credits';
import { FAQS, faqAnchor, type FaqEntry, type FaqTopic } from '@/lib/faq';
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
 * /faq in the site world "The product performs".
 *
 * Every answer is printed in full, grouped by what the visitor is deciding
 * (what it is, what it costs, how to call it, what happens to their data),
 * and three groups sit beside the record that backs them: the credit table,
 * the request, the erase endpoint. No accordion: a closed answer is one the
 * reader has to ask for twice. The JSON-LD and the page read the same `FAQS`,
 * so a crawler and a person get the same words.
 */

const TOPICS: Array<{ topic: FaqTopic; label: string }> = [
  { topic: 'product', label: 'What it is' },
  { topic: 'cost', label: 'What it costs' },
  { topic: 'code', label: 'From your code' },
  { topic: 'data', label: 'Your data' },
];

const byTopic = (topic: FaqTopic) => FAQS.filter((f) => f.topic === topic);


const REQUEST = `curl -N ${absoluteUrl('/api/agent/run')} \\
  -H "Authorization: Bearer $REASONER_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "…", "preset": "auto-budget"}'`;

/** From `erase_user_data` in src/reasoner/api/routes/gdpr.py. */
const ERASED = [
  'Runs, phase by phase',
  'Uploads and their search index',
  'Conversation history',
  'Long-term memory',
  'Cache keys',
  'Usage and billing rows',
];

const CELL = 'px-[var(--space-4)] py-[var(--space-3)]';
const FOOT = 'border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]';

function Answers({ entries }: { entries: readonly FaqEntry[] }) {
  return (
    <>
      {entries.map(({ q, a }) => (
        <div key={q} id={faqAnchor(q)} className="mt-[var(--space-8)] scroll-mt-[var(--space-20)]">
          <h3 className={`font-semibold ${BODY}`}>{q}</h3>
          <p className={`mt-[var(--space-2)] max-w-[60ch] ${BODY}`}>{a}</p>
        </div>
      ))}
    </>
  );
}

export default function FAQPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
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
      <main id="main-content" className="flex-1">
        {/* ── Hero: the promise (left), every question as an index (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Asked first,</span>
              </span>
              <span className="site-line">
                <span>answered here.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                {FAQS.length} questions about what it is, what it costs, how to call it and what
                happens to your data, each answered in full on this page.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/chat" className="site-button">
                  Start reasoning
                </Link>
                <Link href="/docs" className={`site-link ${BODY}`}>
                  Read the documentation
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <nav
              data-ui
              aria-label="Questions on this page"
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              {TOPICS.map(({ topic, label }) => (
                <div key={topic} className={ROW}>
                  <p className="font-semibold">{label}</p>
                  <ul className="mt-[var(--space-1)] list-none">
                    {byTopic(topic).map(({ q }) => (
                      <li key={q} className="py-[var(--space-1)]">
                        <a
                          href={`#${faqAnchor(q)}`}
                          className="text-[var(--site-muted)] underline-offset-4 hover:text-[var(--site-ink)] hover:underline"
                        >
                          {q}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </nav>
          </div>
        </header>

        <Section id="product" lines={['What it is,', 'and why many labs.']}>
          <Answers entries={byTopic('product')} />
          <More href="/how-it-works">Read a complete run</More>
        </Section>

        <Section
          id="cost"
          lines={['What a run', 'costs you.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>
                {CREDITS_PER_USD.toLocaleString('en-US')} credits = $1.00 of model spend
              </figcaption>
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-[var(--site-line)] text-[var(--site-muted)]">
                    <th scope="col" className={`${CELL} font-normal`}>
                      Kind of run
                    </th>
                    <th scope="col" className={`${CELL} text-right font-normal`}>
                      Credits
                    </th>
                    <th scope="col" className={`${CELL} text-right font-normal`}>
                      On Free
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {RUN_COSTS.map(({ kind, cost }) => (
                    <tr key={kind} className="border-b border-[var(--site-line)] last:border-b-0">
                      <th scope="row" className={`${CELL} font-semibold`}>
                        {kind}
                      </th>
                      <td className={`${CELL} text-right nums-tabular`}>
                        {cost[0] === cost[1] ? cost[0] : `${cost[0]}–${cost[1]}`}
                      </td>
                      <td className={`${CELL} text-right nums-tabular`}>{runsPerMonth(FREE_CREDITS, cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className={FOOT}>
                Free grants {FREE_CREDITS.toLocaleString('en-US')} credits a month; the last column is runs
                a month on it.
              </p>
            </figure>
          }
        >
          <Answers entries={byTopic('cost')} />
          <More href="/pricing">Compare the plans</More>
        </Section>

        <Section
          id="code"
          lines={['Calling it', 'from your code.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>One streamed run</figcaption>
              <pre tabIndex={0} className="overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]">
                <code>{REQUEST}</code>
              </pre>
              <p className={FOOT}>Out of credits, the next run returns HTTP 402.</p>
            </figure>
          }
        >
          <Answers entries={byTopic('code')} />
          <More href="/developers">The full developer reference</More>
        </Section>

        <Section
          id="data"
          lines={['What happens', 'to your data.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>
                What <code>DELETE /api/user/data</code> erases
              </figcaption>
              <ul className="list-none">
                {ERASED.map((item) => (
                  <li key={item} className={ROW}>
                    {item}
                  </li>
                ))}
              </ul>
              <p className={FOOT}>Your account itself is deleted separately, from settings.</p>
            </figure>
          }
        >
          <Answers entries={byTopic('data')} />
          <More href="/privacy">Every store, listed</More>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Not answered</span>
            <span className="block">on this page?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>Ask us directly, or read the documentation.</p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/contact" className="site-button">
              Get in touch
            </Link>
            <Link href="/docs" className={`site-link ${BODY}`}>
              Read the documentation
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
