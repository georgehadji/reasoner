import type { Metadata } from 'next';
import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import {
  ArgumentBody as Body,
  ArgumentSection as Section,
  BODY,
  CAP,
  FIGURE,
  HEAD,
  More,
  ROW,
} from '@/components/site/ArgumentSection';
import { HEALTH_CHECKS, OVERALL } from '@/lib/status-checks';
import { SITE, absoluteUrl } from '@/lib/site';
import { StatusClient } from './StatusClient';

export const metadata: Metadata = {
  title: 'Status',
  description: 'Live health of the Reasoner API, checked when the page loads and every 30 seconds after.',
  alternates: { canonical: absoluteUrl('/status') },
  openGraph: {
    title: `Status — ${SITE.name}`,
    description: 'Live health of the API, checked when the page loads.',
    url: absoluteUrl('/status'),
    type: 'website',
  },
};

/**
 * /status in the site world "The product performs".
 *
 * The hero is the live check itself. The sections say what each line tests,
 * how the one-word verdict is chosen, the response as served, and what the
 * page does not measure. Check descriptions come from `lib/status-checks.ts`,
 * mirrored from `health_service.py`.
 *
 * Corrected 2026-11-14: the proxy asked the backend root, which has no
 * `status` field, so this page read "Service disruption" while the API was up.
 */

const RULE = [
  { when: 'Any check reports Error', reads: OVERALL.unhealthy },
  { when: 'Otherwise, any Warning or Degraded', reads: OVERALL.degraded },
  { when: 'Otherwise', reads: OVERALL.healthy },
  { when: 'No answer within 6 seconds', reads: OVERALL.unreachable },
];

const RESPONSE = JSON.stringify(
  {
    status: 'healthy',
    timestamp: '<ISO 8601, UTC>',
    version: '2.0',
    checks: Object.fromEntries(HEALTH_CHECKS.map(({ key }) => [key, { status: 'ok' }])),
  },
  null,
  2,
);

const ABSENT = [
  'Uptime history or an uptime percentage',
  'An incident log',
  'Monitoring from outside our own servers',
  'Each model provider on its own line',
];

export default function StatusPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Hero: what the page is (left), the live check (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Checked as</span>
              </span>
              <span className="site-line">
                <span>you load it.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                The health of the {SITE.name} API, asked when this page opens and every 30 seconds after. Nothing
                is stored, so there is no uptime figure: none is measured.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <a href="#checks" className="site-button">
                  What each check tests
                </a>
                <Link href="/contact" className={`site-link ${BODY}`}>
                  Report a problem
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <StatusClient />
          </div>
        </header>

        <Section
          id="checks"
          lines={['What each line', 'actually tests.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>The six checks, in the order the API reports them</figcaption>
              <ul className="list-none">
                {HEALTH_CHECKS.map(({ key, name, tests, fails }) => (
                  <li key={key} className={ROW}>
                    <p className="font-semibold">{name}</p>
                    <p className="mt-[var(--space-1)]">{tests}.</p>
                    <p className="mt-[var(--space-1)] text-[var(--site-muted)]">{fails}.</p>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            Each line is a probe the API runs on itself when asked. Two of them prove less than their names
            suggest: the response cache always reports OK, and billing only confirms a Stripe key is set
            without calling Stripe.
          </Body>
          <Body>
            A dependency this deployment does not use reads &ldquo;Not configured&rdquo; and counts as OK.
          </Body>
        </Section>

        <Section
          id="verdict"
          lines={['How the one word', 'is chosen.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>From the checks to the headline, first match wins</figcaption>
              <ol className="list-none">
                {RULE.map(({ when, reads }, i) => (
                  <li key={reads} className={`grid grid-cols-[auto_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold nums-tabular">{i + 1}</span>
                    <span>
                      {when}: <span className="font-semibold">{reads}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </figure>
          }
        >
          <Body>
            The API decides the first three; this page adds the fourth when its request fails or the backend
            does not answer in time. Failure reasons are not shown here: they are raw error text, written for
            the people running the service.
          </Body>
        </Section>

        <Section
          id="response"
          lines={['The response,', 'as served.']}
          figure={
            <figure data-ui className={`${FIGURE} min-w-0`}>
              <figcaption className={CAP}>
                <code className="font-mono">GET /api/health</code>, the public shape
              </figcaption>
              <pre className="overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]">
                <code>{RESPONSE}</code>
              </pre>
            </figure>
          }
        >
          <Body>
            Anyone can call it, and your own monitoring can poll it. It answers 200 whatever the verdict, so
            read the <code className="font-mono">status</code> field rather than the HTTP code.
          </Body>
          <Body>Operators holding the admin key also get memory figures and the names of open circuits.</Body>
          <More href="/developers">Calling the API from your code</More>
        </Section>

        <Section
          id="absent"
          lines={['What this page', 'does not show.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Not published yet</figcaption>
              <ul className="list-none">
                {ABSENT.map((item) => (
                  <li key={item} className={`grid grid-cols-[minmax(0,1fr)_auto] gap-[var(--space-3)] ${ROW}`}>
                    <span>{item}</span>
                    <span>None</span>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            This is a snapshot, not a record. A provider that starts failing shows here only once its circuit
            breaker opens, and a fault between two checks may never appear at all.
          </Body>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Something wrong</span>
            <span className="block">that this misses?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            Tell us what you ran and when. A report from you is the only incident record this page has.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/contact" className="site-button">
              Report a problem
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
