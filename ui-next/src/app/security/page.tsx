import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { SecuritySheet } from '@/components/site/SecuritySheet';
import { PROVIDERS } from '@/lib/capabilities.generated';
import { securityTxtLines } from '@/lib/security-txt';

/**
 * /security in the site world "The product performs" (spec/art-direction.md).
 * Order: what holds today (filterable controls) → where a request goes →
 * running it inside your own network → how to report a vulnerability.
 *
 * Claims are only what the code supports; anything unconfirmed carries an
 * [INPUT REQUIRED] note rather than a guess.
 */

/** Services in docker-compose.yml at the repo root, with their images or
 *  build contexts as written there. */
const COMPOSE_SERVICES = [
  ['caddy', 'caddy:2-alpine'],
  ['frontend', 'build ./ui-next'],
  ['backend', 'build .'],
  ['postgres', 'postgres:16-alpine'],
  ['valkey', 'valkey/valkey:8.1.8'],
  ['sandbox-worker', 'build'],
  ['docker-socket-proxy', 'tecnativa/docker-socket-proxy:0.2.0'],
  ['cert-generator', 'alpine:3.24.1'],
] as const;

/** The path a hosted request takes, hop by hop, with what protects each hop. */
const HOPS = [
  { from: 'Your browser', to: 'Reasoner', link: 'HTTPS with HSTS' },
  { from: 'Reasoner', to: 'OpenRouter', link: 'TLS; stored fields encrypted at rest' },
  { from: 'OpenRouter', to: 'Model provider', link: 'TLS; decrypted by the provider to answer' },
] as const;

const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';

export default function SecurityPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        <SecuritySheet
          headline={
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Security,</span>
              </span>
              <span className="site-line">
                <span>as it stands.</span>
              </span>
            </h1>
          }
          lede={
            <>
              <p className="mt-[var(--space-8)] max-w-[44ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                What is built, what is not, and what we still have to confirm, each with its status.
                Nothing here is a compliance certification.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/contact" className="site-button">
                  Ask about security
                </Link>
                <a href="#controls" className={`site-link ${BODY}`}>
                  Read every control
                </a>
              </div>
            </>
          }
        />

        {/* ── Where a request goes: statement left, path fragment right ── */}
        <section
          id="path"
          aria-labelledby="path-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center"
        >
          <div className="lg:col-span-5">
            <h2 id="path-h" className={HEAD}>
              Where a request goes.
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              Through OpenRouter to one or more of the model providers below, each under its own terms.
              We do not sell your data. Every company a request can reach is listed on{' '}
              <Link href="/subprocessors" className="site-link">
                sub-processors
              </Link>
              .
            </p>
          </div>

          <figure
            data-ui
            data-reveal
            className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
          >
            <figcaption className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold">
              Request path, hosted service
            </figcaption>
            <ol className="list-none px-[var(--space-4)] py-[var(--space-2)]">
              {HOPS.map(({ from, to, link }) => (
                <li
                  key={from}
                  className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-[var(--space-3)] border-b border-[var(--site-line)] py-[var(--space-3)] last:border-b-0"
                >
                  <span className="font-semibold">
                    {from} <span aria-hidden="true">&rarr;</span>
                    <span className="sr-only"> to </span> {to}
                  </span>
                  <span className="text-[var(--site-muted)]">{link}</span>
                </li>
              ))}
            </ol>
            <div className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
              <p className="text-[var(--site-muted)]">Providers a request can reach</p>
              <ul className="mt-[var(--space-2)] flex list-none flex-wrap gap-[var(--space-2)]">
                {PROVIDERS.map((name) => (
                  <li key={name} className="rounded-[var(--radius)] border border-[var(--site-line)] px-[var(--space-2)] py-[var(--space-1)]">
                    {name}
                  </li>
                ))}
              </ul>
            </div>
          </figure>
        </section>

        {/* ── Self-hosting: light field, fragment left, statement right ── */}
        <section id="self-host" aria-labelledby="self-host-h" className="bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center">
            <figure
              data-ui
              data-reveal
              className="order-last w-full min-w-0 rounded-[var(--radius-lg)] bg-[var(--site-bg)] text-[var(--site-ink)] lg:order-none lg:col-span-6"
            >
              <figcaption className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold">
                docker-compose.yml
              </figcaption>
              <pre tabIndex={0} className="overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]">
                <code>
                  <span className="text-[var(--site-muted)]">$ </span>docker compose up -d{'\n\n'}
                  {COMPOSE_SERVICES.map(([name, image]) => (
                    <span key={name} className="block">
                      {name.padEnd(21)}
                      <span className="text-[var(--site-muted)]">{image}</span>
                    </span>
                  ))}
                </code>
              </pre>
            </figure>

            <div className="lg:col-span-5 lg:col-start-8">
              <h2 id="self-host-h" className={HEAD}>
                <span className="block">Or run it inside</span>
                <span className="block">your network.</span>
              </h2>
              <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
                The code is source-available under the Business Source License 1.1, which permits
                self-hosting and converts to Apache-2.0 in 2030. The whole stack runs from one Compose
                file in your own infrastructure; then only the model calls you configure leave your
                network.
              </p>
            </div>
          </div>
        </section>

        {/* ── Disclosure: statement, then the file as served ── */}
        <section
          id="disclosure"
          aria-labelledby="disclosure-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <div className="lg:col-span-5">
            <h2 id="disclosure-h" className={HEAD}>
              Report a vulnerability.
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              The disclosure contact is in our security.txt (RFC 9116), shown here exactly as it is
              served. Ask about data retention, self-hosting or our compliance roadmap the same way.
            </p>
            <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
              <Link href="/contact" className="site-button">
                Contact us
              </Link>
              <Link href="/docs" className={`site-link ${BODY}`}>
                Read the docs
              </Link>
            </div>
          </div>

          <figure
            data-ui
            data-reveal
            className="flex min-h-[var(--site-fragment-min-h)] w-full min-w-0 flex-col self-end rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
          >
            <figcaption className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold">
              <a href="/.well-known/security.txt" className="hover:underline">
                /.well-known/security.txt
              </a>
            </figcaption>
            <pre tabIndex={0} className="flex-1 overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]">
              <code>{securityTxtLines().join('\n')}</code>
            </pre>
          </figure>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
