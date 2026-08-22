'use client';

import { useMemo, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ArrowLeft, ArrowRight, ArrowUpRight } from 'lucide-react';

import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import {
  FEATURED_ROUTES,
  sanitizeDisplayPath,
  suggestRoutes,
} from '@/lib/route-suggestions';

/**
 * 404.
 *
 * The brief was "high-end", which here means the page is written in the
 * product's own voice rather than borrowed from the genre. Reasoner's whole
 * claim is that an answer it cannot verify gets labelled UNKNOWN instead of
 * guessed at; a missing route is exactly that case, so the page presents itself
 * as a pipeline verdict — status, evidence, ranked recovery — using the same
 * epistemic vocabulary and the same tokens as a synthesis card.
 *
 * The order of the page is the order of usefulness, not the order of drama:
 *   1. what happened, in one line
 *   2. the address that failed, quoted back so the visitor can spot the typo
 *   3. the best guess at where they meant to go, with its confidence shown
 *   4. the two actions worth taking
 *   5. a short list of real destinations
 *   6. a way to report the broken link
 *
 * Published guidance on error pages agrees on three things: state the problem
 * in plain language, do not blame the visitor, and offer a small ranked set of
 * ways out rather than a sitemap dump. The ranking work happens in
 * `lib/route-suggestions.ts`; this file is presentation.
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
  const best = suggestions[0];

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

  /* One shared stagger so the sections arrive in reading order. `--stagger-step`
     is 40ms, so the last block lands inside the 200ms "instant" window.
     `animate-phase-reveal` sets `animation-fill-mode: both`, which is what makes
     a delayed entrance safe — a `forwards` animation paints at full opacity
     through its own delay, then snaps to zero before fading in. */
  const stagger = (step: number) => ({
    animationDelay: `calc(var(--stagger-step) * ${step})`,
  });

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main
        id="main-content"
        className="relative isolate mx-auto w-full max-w-3xl flex-1 px-6 py-20 sm:py-28"
      >
        {/* Ambient wash behind the statement. Decorative only: it carries no
            information, so it is hidden from assistive tech and cannot be hit. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-72 opacity-70"
          style={{
            background:
              'radial-gradient(60% 100% at 50% 0%, var(--accent-dim) 0%, transparent 70%)',
          }}
        />

        {/* ── 1. Verdict ─────────────────────────────────────────── */}
        <div className="animate-phase-reveal" style={stagger(0)}>
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-mono text-[length:var(--text-2xs)] uppercase tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
              Error 404
            </span>
            <span aria-hidden="true" className="h-px w-6 bg-[var(--border-strong)]" />
            {/* The dotted rule is the one a synthesis card uses for a claim it
                cannot verify, so the label means the same thing here. */}
            <span className="epistemic-unknown pl-2.5 font-mono text-[length:var(--text-2xs)] font-semibold uppercase tracking-[var(--tracking-label)]">
              Unknown
            </span>
          </div>

          <h1 className="mt-6 font-serif text-[length:var(--text-4xl)] leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)]">
            This address returns nothing we can verify.
          </h1>

          <p className="mt-5 max-w-xl text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
            There is no page here. The link may be out of date, or the URL may
            have picked up a typo on the way. Nothing is wrong with your account
            and nothing was lost.
          </p>
        </div>

        {/* ── 2. Evidence ────────────────────────────────────────── */}
        <div
          className="animate-phase-reveal mt-10 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)]"
          style={stagger(1)}
        >
          <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] px-4 py-2.5">
            <span className="font-mono text-[length:var(--text-2xs)] uppercase tracking-[var(--tracking-label)] text-[var(--text-muted)]">
              Requested
            </span>
            <span className="font-mono text-[length:var(--text-2xs)] font-semibold text-[var(--red)]">
              404
            </span>
          </div>
          {/* The path is attacker-chosen — anyone can send a link and pick what
              this line says. `sanitizeDisplayPath` has already removed the
              control and bidi characters and capped the length; `break-all`
              handles the rest without a horizontal scrollbar. */}
          <p className="break-all px-4 py-3 font-mono text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text)]">
            {requestedPath}
          </p>
        </div>

        {/* ── 3. Best guess ──────────────────────────────────────── */}
        {best && (
          <section
            className="animate-phase-reveal mt-10"
            style={stagger(2)}
            aria-labelledby="did-you-mean"
          >
            <h2
              id="did-you-mean"
              className="font-mono text-[length:var(--text-2xs)] uppercase tracking-[var(--tracking-label)] text-[var(--text-muted)]"
            >
              Closest match
            </h2>

            <Link
              href={best.href}
              className="group mt-3 flex items-center gap-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-5 py-4 transition-all duration-[var(--dur-state)] hover:-translate-y-px hover:border-[var(--border-strong)] hover:shadow-[var(--shadow)]"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-[length:var(--text-lg)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
                  {best.label}
                </span>
                <span className="mt-1 block truncate font-mono text-[length:var(--text-xs)] text-[var(--text-muted)]">
                  {best.href}
                </span>
              </span>
              {/* Confidence is stated as a number, not only as a bar width: a
                  bar alone is unreadable to a screen reader and invisible in
                  monochrome. */}
              <span className="hidden shrink-0 text-right sm:block">
                <span className="block font-mono text-[length:var(--text-xs)] tabular-nums text-[var(--text-2)]">
                  {Math.round(best.score * 100)}% match
                </span>
                <span
                  aria-hidden="true"
                  className="mt-1.5 block h-1 w-24 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--surface-3)]"
                >
                  <span
                    className="block h-full rounded-[var(--radius-pill)] bg-[var(--accent)]"
                    style={{ width: `${Math.round(best.score * 100)}%` }}
                  />
                </span>
              </span>
              <ArrowRight
                aria-hidden="true"
                className="h-4 w-4 shrink-0 text-[var(--text-subtle)] transition-transform duration-[var(--dur-micro)] group-hover:translate-x-0.5 group-hover:text-[var(--accent)]"
              />
            </Link>

            {suggestions.length > 1 && (
              <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[length:var(--text-xs)] text-[var(--text-muted)]">
                <span>Or</span>
                {suggestions.slice(1).map((route) => (
                  <Link
                    key={route.href}
                    href={route.href}
                    className="font-mono text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 transition-colors duration-[var(--dur-micro)] hover:text-[var(--accent)] hover:decoration-[var(--accent)]"
                  >
                    {route.href}
                  </Link>
                ))}
              </p>
            )}
          </section>
        )}

        {/* ── 4. Actions ─────────────────────────────────────────── */}
        <div
          className="animate-phase-reveal mt-10 flex flex-wrap items-center gap-3"
          style={stagger(3)}
        >
          <Link
            href="/chat"
            className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[var(--accent)] px-6 text-[length:var(--text-base)] font-semibold text-[var(--accent-text)] transition-all duration-[var(--dur-state)] hover:-translate-y-px hover:bg-[var(--accent-hover)] hover:shadow-[var(--accent-glow)] active:translate-y-0 active:scale-[0.97]"
          >
            Ask Reasoner instead
            <ArrowUpRight aria-hidden="true" className="h-4 w-4" />
          </Link>

          <Link
            href="/"
            className="inline-flex h-12 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-6 text-[length:var(--text-base)] font-medium text-[var(--text)] transition-all duration-[var(--dur-state)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-3)] active:scale-[0.97]"
          >
            Back to home
          </Link>

          {canGoBack && (
            <button
              type="button"
              onClick={() => router.back()}
              className="inline-flex h-12 items-center justify-center gap-1.5 rounded-xl px-4 text-[length:var(--text-sm)] font-medium text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] hover:bg-[var(--surface-hover)] hover:text-[var(--text)]"
            >
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
              Previous page
            </button>
          )}
        </div>

        {/* ── 5. Destinations ────────────────────────────────────── */}
        <section
          className="animate-phase-reveal mt-16 border-t border-[var(--border)] pt-10"
          style={stagger(4)}
          aria-labelledby="destinations"
        >
          <h2
            id="destinations"
            className="font-mono text-[length:var(--text-2xs)] uppercase tracking-[var(--tracking-label)] text-[var(--text-muted)]"
          >
            Where people usually go
          </h2>

          {/* Six, not the whole sitemap. Someone who is already lost does not
              need more choices, they need fewer and better ones. */}
          <ul className="mt-5 grid gap-x-8 sm:grid-cols-2">
            {FEATURED_ROUTES.map((route) => (
              <li key={route.href}>
                <Link
                  href={route.href}
                  className="group flex items-baseline gap-3 rounded-[var(--radius)] py-3"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-[length:var(--text-base)] font-medium text-[var(--text)] transition-colors duration-[var(--dur-micro)] group-hover:text-[var(--accent)]">
                      {route.label}
                    </span>
                    <span className="mt-0.5 block text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
                      {route.blurb}
                    </span>
                  </span>
                  <ArrowRight
                    aria-hidden="true"
                    className="h-3.5 w-3.5 shrink-0 -translate-x-1 text-[var(--text-subtle)] opacity-0 transition-all duration-[var(--dur-micro)] group-hover:translate-x-0 group-hover:text-[var(--accent)] group-hover:opacity-100"
                  />
                </Link>
              </li>
            ))}
          </ul>
        </section>

        {/* ── 6. Report ──────────────────────────────────────────── */}
        <p
          className="animate-phase-reveal mt-12 text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-subtle)]"
          style={stagger(5)}
        >
          Followed a link on this site to get here?{' '}
          <Link
            href="/contact"
            className="underline decoration-[var(--border-strong)] underline-offset-4 transition-colors duration-[var(--dur-micro)] hover:text-[var(--accent)] hover:decoration-[var(--accent)]"
          >
            Tell us
          </Link>{' '}
          and we will fix it.
        </p>
      </main>

      <SiteFooter />
    </div>
  );
}
