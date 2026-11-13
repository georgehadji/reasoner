import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { DataRegistry } from '@/components/site/DataRegistry';
import { PROVIDERS } from '@/lib/capabilities.generated';
import { ERASED_BY_DATA_DELETE, USER_DATA_STORES } from '@/lib/user-data-stores';

/**
 * /privacy in the site world "The product performs" (spec/art-direction.md).
 * Order: where an account's data lives (live erasure preview) → what we keep
 * and why → who else reads a request → export and erase → what is not
 * decided yet.
 *
 * Sources: src/reasoner/api/user_data.py (store registry),
 * api/routes/gdpr.py and application/services/data_eraser.py (erasure and
 * its receipt), infrastructure/persistence/user_data_pg.py (profile, usage
 * and billing fields), security/encryption.py (at-rest formats).
 */

const KEPT = [
  {
    term: 'Your account',
    detail:
      'Email address, sign-in provider, avatar, when you signed up and last signed in. Sign-in and account events are logged with time, IP address and user agent.',
  },
  {
    term: 'Your runs and files',
    detail:
      'Every run, phase by phase, your conversation history and uploads, so you can return to them. Runs, uploads and their search index are encrypted before they are stored.',
  },
  {
    term: 'Usage and billing',
    detail:
      'For each run: preset, method, tokens in and out, cost and time. Card details go to Stripe or PayPal; we keep their customer and subscription IDs.',
  },
  {
    term: 'What we do not do',
    detail: 'We do not train or fine-tune models on your data, and we do not sell it. You keep ownership of your inputs and outputs.',
  },
] as const;

const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
const FIG = 'w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)]';
const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';
const PRE = 'flex-1 overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]';

export default function PrivacyPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        <DataRegistry
          headline={
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Your data, and</span>
              </span>
              <span className="site-line">
                <span>what we keep.</span>
              </span>
            </h1>
          }
          lede={
            <>
              <p className="mt-[var(--space-8)] max-w-[44ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Our privacy policy, written from the code: every place an account&rsquo;s data is
                stored, and the two ways to remove it.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/contact" className="site-button">
                  Ask about your data
                </Link>
                <a href="#rights" className={`site-link ${BODY}`}>
                  Export or erase it
                </a>
              </div>
            </>
          }
        />

        {/* ── What we keep: heading left, terms right ── */}
        <section
          id="kept"
          aria-labelledby="kept-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <h2 id="kept-h" className={`${HEAD} lg:col-span-4`}>
            <span className="block">What we keep,</span>
            <span className="block">and why.</span>
          </h2>
          <dl className="space-y-[var(--space-10)] lg:col-span-7 lg:col-start-6">
            {KEPT.map(({ term, detail }) => (
              <div key={term}>
                <dt className="font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)]">{term}</dt>
                <dd className={`mt-[var(--space-3)] ${BODY}`}>{detail}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* ── Providers: light field, fragment left, statement right ── */}
        <section id="providers" aria-labelledby="providers-h" className="bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center">
            <figure
              data-ui
              data-reveal
              className="order-last flex min-h-[var(--site-fragment-min-h)] w-full min-w-0 flex-col rounded-[var(--radius-lg)] bg-[var(--site-bg)] text-[var(--site-ink)] lg:order-none lg:col-span-6"
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
                Routed through OpenRouter, over TLS. Each is listed with its privacy policy on{' '}
                <Link href="/subprocessors" className="text-[var(--site-ink)] underline underline-offset-4">
                  sub-processors
                </Link>
                .
              </p>
            </figure>

            <div className="lg:col-span-5 lg:col-start-8">
              <h2 id="providers-h" className={HEAD}>
                <span className="block">Who else reads</span>
                <span className="block">a request.</span>
              </h2>
              <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
                To answer, your problem goes to one or more of these model providers, which decrypt it
                to process it, so this is not end-to-end encryption. Each handles API traffic under its
                own terms. [INPUT REQUIRED: which providers may retain or train on API traffic, and
                does our OpenRouter account enforce a no-training setting?]
              </p>
            </div>
          </div>
        </section>

        {/* ── Rights: statement, then the two fragments side by side ── */}
        <section
          id="rights"
          aria-labelledby="rights-h"
          className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]"
        >
          <div className="grid gap-[var(--space-8)] lg:grid-cols-12">
            <h2 id="rights-h" className={`${HEAD} lg:col-span-5`}>
              <span className="block">Take it with you,</span>
              <span className="block">or erase it.</span>
            </h2>
            <div className={`space-y-[var(--space-4)] lg:col-span-6 lg:col-start-7 ${BODY}`}>
              <p>
                Export returns every store above as one JSON document; if any store fails, the export
                fails rather than look complete. Erasing your data keeps your account; deleting your
                account, from{' '}
                <Link href="/settings" className="site-link">
                  settings
                </Link>
                , removes everything and cancels billing. Both are permanent.
              </p>
              <p>
                Export and data erasure are API calls today, with an API key; or ask us through{' '}
                <Link href="/contact" className="site-link">
                  contact
                </Link>{' '}
                and we will run them for you.
              </p>
            </div>
          </div>

          <div className="mt-[var(--space-16)] grid gap-[var(--space-8)] lg:grid-cols-2">
            <figure data-ui data-reveal className={`flex min-h-[var(--site-fragment-min-h)] flex-col ${FIG}`}>
              <figcaption className={CAP}>
                <code className="font-mono">GET /api/account/export</code>
              </figcaption>
              <pre className={PRE}>
                <code>
                  {'{\n'}
                  {USER_DATA_STORES.map((s, i) => (
                    <span key={s.name} className="block">
                      {'  '}&quot;{s.name}&quot;: <span className="text-[var(--site-muted)]">…</span>
                      {i < USER_DATA_STORES.length - 1 ? ',' : ''}
                    </span>
                  ))}
                  {'}'}
                </code>
              </pre>
            </figure>

            <figure data-ui data-reveal className={`flex min-h-[var(--site-fragment-min-h)] flex-col ${FIG}`}>
              <figcaption className={CAP}>
                <code className="font-mono">DELETE /api/user/data</code>
                <span className="font-normal text-[var(--site-muted)]">, the receipt</span>
              </figcaption>
              <pre className={PRE}>
                <code>
                  {'{\n  "status": "completed",\n  "erased": [\n'}
                  {ERASED_BY_DATA_DELETE.map((name, i) => (
                    <span key={name} className="block">
                      {'    '}&quot;{name}&quot;{i < ERASED_BY_DATA_DELETE.length - 1 ? ',' : ''}
                    </span>
                  ))}
                  {'  ],\n  "failed": [],\n  "timestamp": '}
                  <span className="text-[var(--site-muted)]">…</span>
                  {'\n}'}
                </code>
              </pre>
            </figure>
          </div>
        </section>

        {/* ── Not decided yet ── */}
        <section
          id="open"
          aria-labelledby="open-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] pb-[var(--space-24)] lg:grid-cols-12"
        >
          <h2 id="open-h" className={`${HEAD} lg:col-span-4`}>
            Not decided yet.
          </h2>
          <div className={`space-y-[var(--space-4)] lg:col-span-7 lg:col-start-6 ${BODY}`}>
            <p>
              We do not yet publish a fixed retention period: data stays until you erase it or close
              your account. [INPUT REQUIRED: retention period, if any.] A mode that stores nothing after
              a run is planned, not built.
            </p>
            <p>
              Cookies are covered on{' '}
              <Link href="/cookies" className="site-link">
                cookies
              </Link>
              ; how the data is protected, on{' '}
              <Link href="/security" className="site-link">
                security
              </Link>
              .
            </p>
            <p className="text-[var(--site-muted)]">Effective [INPUT REQUIRED: effective date of this policy].</p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
