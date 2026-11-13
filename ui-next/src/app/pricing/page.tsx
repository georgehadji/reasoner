'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { apiFetch } from '@/lib/api-client';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CreditCalculator } from '@/components/site/CreditCalculator';
import { CREDITS_PER_USD, TIER_CREDITS } from '@/lib/credits';

/**
 * /pricing in the site world "The product performs" (spec/art-direction.md).
 * Order: the meter, live (how far each plan's credits go) → the three plans
 * → when you are charged → the meter's public endpoint.
 *
 * Credit figures mirror src/reasoner/domain/credits.py via lib/credits.ts.
 * Prices are owner decisions and stay [INPUT REQUIRED]. Enterprise is a
 * real tier in the backend but sold on agreed terms, so it links to contact.
 */

const PLAN_DETAIL: Record<string, { price: string; includes: string }> = {
  free: { price: '[INPUT REQUIRED: Free plan price]', includes: 'Budget presets and web search.' },
  pro: { price: '[INPUT REQUIRED: Pro plan price]', includes: 'Budget and Premium presets, Neuro memory, deep research.' },
  enterprise: { price: 'Agreed with you', includes: 'Self-hosted deployment, service levels and volume terms.' },
};

/** CreditReason in domain/credits.py, split by _CREDIT_REASONS. */
const LEDGER_IN = ['signup_bonus', 'monthly_grant', 'purchase', 'refund', 'admin_adjustment'] as const;
const LEDGER_OUT = ['pipeline_run', 'web_search', 'image_generation'] as const;

/** GET /api/credits/pricing, as the backend returns it. */
const PRICING_RESPONSE = JSON.stringify(
  {
    credits_per_usd: CREDITS_PER_USD,
    usd_per_credit: 1 / CREDITS_PER_USD,
    tier_monthly_allowance: Object.fromEntries(TIER_CREDITS.map((t) => [t.tier, t.credits])),
    reasons: ['signup_bonus', 'monthly_grant', 'purchase', 'admin_adjustment', 'refund', 'pipeline_run', 'image_generation', 'web_search'],
  },
  null,
  2,
);

function isValidCheckoutUrl(url: string): boolean {
  try {
    const u = new URL(url);
    // Stripe checkout URLs
    if (u.protocol === 'https:' && u.hostname.endsWith('.stripe.com')) return true;
    // PayPal checkout/approval URLs
    if (u.protocol === 'https:' && (u.hostname === 'www.paypal.com' || u.hostname === 'www.sandbox.paypal.com')) return true;
    return false;
  } catch {
    return false;
  }
}

const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';
const PAY =
  'inline-flex min-h-[var(--space-10)] items-center justify-center rounded-[var(--radius)] px-[var(--space-4)] font-semibold transition-colors duration-[var(--dur-micro)] disabled:opacity-40';

export default function PricingPage() {
  // One action at a time across every tier/provider button (U7).
  const checkout = useAsyncAction();
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  // `ok` means the redirect has started: keep the buttons locked until the page unloads.
  const locked = checkout.status === 'pending' || checkout.status === 'ok';
  const handleUpgrade = (tier: string, provider: 'stripe' | 'paypal') =>
    checkout.run(`${tier}:${provider}`, async () => {
      const res = await apiFetch(
        `/api/billing/checkout?tier=${encodeURIComponent(tier)}&provider=${provider}`,
        { method: 'POST' }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Checkout failed (HTTP ${res.status})`);
      }
      const data = await res.json();
      const url = data.checkout_url;
      if (!url || typeof url !== 'string' || !isValidCheckoutUrl(url)) {
        throw new Error('Invalid checkout URL received');
      }
      // A checkout redirect is a genuine event-handler side effect; do it here, not via state.
      window.location.href = url;
    }, 'Checkout failed');

  const isLoading = (tier: string, provider: 'stripe' | 'paypal') =>
    checkout.pending && checkout.key === `${tier}:${provider}`;

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: statement left, the live meter right ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Pay only for</span>
              </span>
              <span className="site-line">
                <span>what ran.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[44ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Every plan is a monthly allowance of credits. 1,000 credits are $1.00 of model spend,
                charged after each run from what it actually cost.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/chat" className="site-button">
                  Start free
                </Link>
                <a href="#plans" className={`site-link ${BODY}`}>
                  Compare plans
                </a>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <CreditCalculator />
          </div>
        </header>

        {/* ── Plans: heading left, the plan sheet right ── */}
        <section
          id="plans"
          aria-labelledby="plans-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <div className="lg:col-span-4">
            <h2 id="plans-h" className={HEAD}>
              <span className="block">Three plans,</span>
              <span className="block">one meter.</span>
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[36ch] ${BODY}`}>
              The allowance tops up at the start of each billing period. Card payments go through
              Stripe; PayPal works too.
            </p>
          </div>

          <figure data-ui data-reveal className="min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-8">
            <figcaption className={CAP}>Plans</figcaption>
            {checkout.error && (
              <p role="alert" className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--red)]">
                {checkout.error}
              </p>
            )}
            <ul className="list-none">
              {TIER_CREDITS.map(({ tier, name, credits }) => {
                const { price, includes } = PLAN_DETAIL[tier];
                return (
                  <li
                    key={tier}
                    className="grid gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-5)] last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
                  >
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-baseline gap-x-[var(--space-3)]">
                        <span className="font-display text-[length:var(--site-lead)]">{name}</span>
                        <span className="nums-tabular text-[var(--site-accent)]">
                          {credits.toLocaleString('en-US')} credits a month
                        </span>
                      </p>
                      <p className="mt-[var(--space-1)]">{price}</p>
                      <p className="mt-[var(--space-1)] text-[var(--site-muted)]">{includes}</p>
                    </div>

                    <div className="flex flex-wrap gap-[var(--space-2)] sm:justify-end">
                      {tier === 'free' && (
                        <Link href="/chat" className={`${PAY} border border-[var(--site-line)] hover:bg-[var(--site-surface-2)]`}>
                          Start free
                        </Link>
                      )}
                      {tier === 'enterprise' && (
                        <Link href="/contact?topic=enterprise" className={`${PAY} border border-[var(--site-line)] hover:bg-[var(--site-surface-2)]`}>
                          Talk to us
                        </Link>
                      )}
                      {tier === 'pro' &&
                        (selectedTier === 'pro' ? (
                          <>
                            <button
                              type="button"
                              onClick={() => handleUpgrade('pro', 'stripe')}
                              disabled={locked}
                              aria-busy={isLoading('pro', 'stripe')}
                              className={`${PAY} bg-[var(--site-accent)] text-[var(--site-accent-ink)] hover:opacity-90`}
                            >
                              {isLoading('pro', 'stripe') ? 'Opening…' : 'Pay by card'}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleUpgrade('pro', 'paypal')}
                              disabled={locked}
                              aria-busy={isLoading('pro', 'paypal')}
                              className={`${PAY} border border-[var(--site-line)] hover:bg-[var(--site-surface-2)]`}
                            >
                              {isLoading('pro', 'paypal') ? 'Opening…' : 'PayPal'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setSelectedTier(null)}
                              className={`${PAY} text-[var(--site-muted)] hover:text-[var(--site-ink)]`}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setSelectedTier('pro')}
                            disabled={locked}
                            className={`${PAY} bg-[var(--site-accent)] text-[var(--site-accent-ink)] hover:opacity-90`}
                          >
                            Upgrade to Pro
                          </button>
                        ))}
                    </div>
                  </li>
                );
              })}
            </ul>
          </figure>
        </section>

        {/* ── When you are charged: light field, ledger left, statement right ── */}
        <section id="charged" aria-labelledby="charged-h" className="bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center">
            <figure
              data-ui
              data-reveal
              className="order-last min-h-[var(--site-fragment-min-h)] w-full min-w-0 rounded-[var(--radius-lg)] bg-[var(--site-bg)] text-[var(--site-ink)] lg:order-none lg:col-span-6"
            >
              <figcaption className={CAP}>Why a ledger entry exists</figcaption>
              <div className="grid grid-cols-2 gap-[var(--space-4)] p-[var(--space-4)]">
                {(
                  [
                    ['Adds credits', LEDGER_IN],
                    ['Spends credits', LEDGER_OUT],
                  ] as const
                ).map(([title, reasons]) => (
                  <div key={title}>
                    <p className="text-[var(--site-muted)]">{title}</p>
                    <ul className="mt-[var(--space-2)] list-none space-y-[var(--space-1)]">
                      {reasons.map((r) => (
                        <li key={r}>
                          <code className="font-mono">{r}</code>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
              <p className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
                Append-only: each entry keeps its amount, reason and the balance after it.
              </p>
            </figure>

            <div className="lg:col-span-5 lg:col-start-8">
              <h2 id="charged-h" className={HEAD}>
                <span className="block">Charged after</span>
                <span className="block">the run.</span>
              </h2>
              <div className={`mt-[var(--space-6)] max-w-[44ch] space-y-[var(--space-4)] ${BODY}`}>
                <p>
                  A run that fails before any model is called costs nothing, and so does an answer from
                  the cache. Charges round up to whole credits.
                </p>
                <p>
                  Every charge carries an idempotency key, so a retried request cannot charge twice. If a
                  run takes the balance to zero, the next one waits until the allowance tops up.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── The meter's public endpoint ── */}
        <section
          id="meter"
          aria-labelledby="meter-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <div className="lg:col-span-5">
            <h2 id="meter-h" className={HEAD}>
              <span className="block">Read the meter</span>
              <span className="block">yourself.</span>
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              The rate and every allowance are public, with no key, so a client can show costs before
              anyone signs in. Your balance and ledger are on the API too.
            </p>
            <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
              <Link href="/docs/credits" className="site-button">
                Read how credits work
              </Link>
              <Link href="/contact?topic=enterprise" className={`site-link ${BODY}`}>
                Ask about Enterprise
              </Link>
            </div>
          </div>

          <figure
            data-ui
            data-reveal
            className="flex min-h-[var(--site-fragment-min-h)] w-full min-w-0 flex-col self-end rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
          >
            <figcaption className={CAP}>
              <code className="font-mono">GET /api/credits/pricing</code>
            </figcaption>
            <pre className="flex-1 overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]">
              <code>{PRICING_RESPONSE}</code>
            </pre>
          </figure>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
