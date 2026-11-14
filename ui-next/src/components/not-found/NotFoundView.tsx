'use client';

import { useMemo, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { ArgumentSection as Section, BODY, CAP, FIGURE, ROW } from '@/components/site/ArgumentSection';
import { FEATURED_ROUTES, sanitizeDisplayPath, suggestRoutes } from '@/lib/route-suggestions';

/**
 * 404 in the site world "The product performs".
 *
 * Reasoner labels what it cannot verify UNKNOWN instead of guessing; a missing
 * route is exactly that case, so the page shows the request the way a run
 * shows a claim: the address quoted back, the verdict, and the closest routes
 * with their match scores. Then a short list of real destinations, and a way
 * to report a broken link. The ranking lives in `lib/route-suggestions.ts`;
 * this file is presentation.
 *
 * Client component because the requested path only exists on the client:
 * `not-found.tsx` receives no props, and `usePathname()` is the only route
 * into it.
 */
export function NotFoundView() {
  const router = useRouter();
  const pathname = usePathname();

  const requestedPath = sanitizeDisplayPath(pathname);
  const suggestions = useMemo(() => suggestRoutes(pathname, 3), [pathname]);

  /* `router.back()` in a tab whose first entry is this page is a dead control:
     it looks like a way out and does nothing. Session history is a browser API
     rather than React state, so it is read through `useSyncExternalStore` — the
     server snapshot is `false`, which keeps the button out of the SSR markup
     and out of a hydration mismatch. The subscribe callback is a no-op because
     `history.length` cannot change while this page is the current entry. */
  const canGoBack = useSyncExternalStore(
    () => () => {},
    () => window.history.length > 1,
    () => false,
  );

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), the request as a run would show it (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>No page at</span>
              </span>
              <span className="site-line">
                <span>this address.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                The link may be out of date, or the address picked up a typo. Nothing is wrong
                with your account and nothing was lost.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/chat" className="site-button">
                  Ask Reasoner instead
                </Link>
                <Link href="/" className={`site-link ${BODY}`}>
                  Back to home
                </Link>
                {canGoBack && (
                  <button type="button" onClick={() => router.back()} className={`site-link ${BODY}`}>
                    Previous page
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>The request</figcaption>
              <dl>
                <div className={ROW}>
                  <dt className="text-[var(--site-muted)]">Address</dt>
                  {/* The path is attacker-chosen — anyone can send a link and pick
                      what this line says. `sanitizeDisplayPath` has already removed
                      control and bidi characters and capped the length;
                      `break-all` handles the rest without a horizontal scrollbar. */}
                  <dd className="mt-[var(--space-1)] break-all">
                    <code className="font-mono">{requestedPath}</code>
                  </dd>
                </div>
                <div className={`flex items-baseline justify-between gap-[var(--space-3)] ${ROW}`}>
                  <dt className="text-[var(--site-muted)]">Status</dt>
                  <dd className="nums-tabular">404 Not Found</dd>
                </div>
                <div className={`flex items-baseline justify-between gap-[var(--space-3)] ${ROW}`}>
                  <dt className="text-[var(--site-muted)]">Verdict</dt>
                  {/* The dotted rule a synthesis card uses for a claim it cannot verify. */}
                  <dd className="epistemic-unknown pl-[var(--space-2)] font-semibold">Unknown</dd>
                </div>
              </dl>
              {suggestions.length > 0 && (
                <>
                  <p className={`border-t ${CAP}`}>Closest routes</p>
                  <ol className="list-none">
                    {suggestions.map((route) => (
                      <li
                        key={route.href}
                        className={`flex items-baseline justify-between gap-[var(--space-3)] ${ROW}`}
                      >
                        <Link href={route.href} className="site-link min-w-0 font-semibold text-current">
                          {route.label}
                        </Link>
                        <span className="shrink-0 nums-tabular text-[var(--site-muted)]">
                          {Math.round(route.score * 100)}% match
                        </span>
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </figure>
          </div>
        </header>

        {/* Six, not the whole sitemap: someone who is lost needs fewer, better choices. */}
        <Section
          id="destinations"
          lines={['Or start', 'from here.']}
          figure={
            <figure data-ui data-reveal className={FIGURE}>
              <figcaption className={CAP}>{FEATURED_ROUTES.length} pages</figcaption>
              <ul className="list-none">
                {FEATURED_ROUTES.map((route) => (
                  <li key={route.href} className={ROW}>
                    <Link href={route.href} className="site-link font-semibold text-current">
                      {route.label}
                    </Link>
                    <p className="mt-[var(--space-1)] text-[var(--site-muted)]">{route.blurb}</p>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <p className={BODY}>
            A short list rather than the whole sitemap: where to start, what it does, what it
            costs, and where to get help. The footer lists every other page.
          </p>
        </Section>

        <Section id="report" lines={['Got here from', 'a link of ours?']} field>
          <p className={BODY}>
            Then the broken link is ours.{' '}
            <Link href="/contact" className="site-link font-semibold text-current">
              Tell us which page linked here
            </Link>
            , and quote the address above.
          </p>
        </Section>
      </main>

      <SiteFooter />
    </div>
  );
}
