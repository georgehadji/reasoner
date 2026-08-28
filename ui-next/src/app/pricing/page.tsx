'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { apiFetch } from '@/lib/api-client';
import { Check, X, Shield, CreditCard, Clock, Mail } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { SpotlightCard } from '@/components/ui/SpotlightCard';

// Two self-serve plans. Enterprise stays a real, billable tier in the
// backend (SubscriptionTier.ENTERPRISE, Stripe/PayPal price IDs, spend
// ceilings) — it's just not sold off a fixed-price card here. Volume and
// custom-deployment terms are negotiated, so it's a "contact us" link
// below the cards instead of a third self-serve plan.
const plans = [
  {
    name: 'Free',
    tier: 'free',
    price: '$0',
    period: 'forever',
    queries: '20 queries / month',
    features: [
      'Budget routing presets',
      'Basic web search',
      'Community support',
    ],
    notIncluded: [
      'Premium models',
      'Advanced analytics',
      'Priority support',
    ],
  },
  {
    name: 'Pro',
    tier: 'pro',
    price: '$12',
    period: '/ month',
    queries: '500 queries / month',
    features: [
      'All routing presets (Budget + Premium)',
      'Advanced multi-model consensus',
      'Deep research & iterative RAG',
      'Neuro memory & embedding search',
      'Priority email support',
    ],
    notIncluded: [
      'Custom model deployments',
      'Dedicated infrastructure',
    ],
    highlighted: true,
  },
];

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

export default function PricingPage() {
  const [loadingTier, setLoadingTier] = useState<string | null>(null);
  const [selectedTier, setSelectedTier] = useState<string | null>(null);
  const [error, setError] = useState('');
  // Navigate straight from the handler rather than staging the URL in state and
  // letting an effect perform it. Routing it through state made a repeat click
  // silently do nothing: setState with an Object.is-equal value bails out, so
  // returning via bfcache (which restores state and does not re-run effects) and
  // clicking the same tier again re-set the identical URL, the effect never
  // re-fired, and the button span forever because setLoadingTier(null) only runs
  // in the catch. A checkout redirect is a genuine event-handler side effect.
  const navigateToCheckout = useCallback((url: string) => {
    window.location.href = url;
  }, []);

  const handleUpgrade = async (tier: string, provider: 'stripe' | 'paypal') => {
    setError('');
    setLoadingTier(`${tier}:${provider}`);
    try {
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
      navigateToCheckout(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Checkout failed';
      setError(msg);
      setLoadingTier(null);
    }
  };

  const isLoading = (tier: string, provider: 'stripe' | 'paypal') =>
    loadingTier === `${tier}:${provider}`;

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-12">
        <div className="mb-10 text-center">
          <h1 className="text-3xl font-bold text-[var(--text)]">Simple, Transparent Pricing</h1>
          <p className="mt-2 text-[var(--text-muted)]">Start free. Scale with confidence. No hidden fees.</p>
        </div>

        {error && (
          <div className="mx-auto mb-6 max-w-lg rounded-[var(--radius)] bg-[var(--red-bg)] p-3 text-sm text-[var(--red)]" role="alert">
            <div className="flex items-center gap-2">
              <X className="h-4 w-4 shrink-0" />
              {error}
            </div>
          </div>
        )}

        <div className="mx-auto grid max-w-3xl grid-cols-1 gap-6 sm:grid-cols-2">
          {plans.map((plan) => (
            /* SpotlightCard renders the accent wash and nothing else — the
               border, ring, shadow and padding stay here, so the highlighted
               tier keeps reading as the recommended one whether or not a
               pointer is anywhere near it. */
            <SpotlightCard
              key={plan.name}
              className={`flex flex-col rounded-[var(--radius-lg)] border bg-[var(--surface)] p-6 transition-all ${
                plan.highlighted
                  ? 'border-[var(--border-strong)] shadow-[var(--shadow-lg)] ring-1 ring-[color-mix(in_oklab,var(--accent)_20%,transparent)]'
                  : 'border-[var(--border)] hover:shadow-[var(--shadow-lg)]'
              }`}
            >
              {plan.highlighted && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-[var(--accent)] px-3 py-0.5 text-xs font-semibold text-[var(--accent-text)]">
                  Recommended
                </div>
              )}

              <div className="mb-4">
                <h2 className="text-lg font-semibold text-[var(--text)]">{plan.name}</h2>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-4xl font-bold text-[var(--text)]">{plan.price}</span>
                  <span className="text-sm text-[var(--text-muted)]">{plan.period}</span>
                </div>
                <p className="mt-1 text-sm text-[var(--text-muted)]">{plan.queries}</p>
              </div>

              <ul className="mb-4 flex-1 space-y-2.5 text-left text-sm text-[var(--text-2)]">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-[var(--accent)]" />
                    <span>{f}</span>
                  </li>
                ))}
                {plan.notIncluded?.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-[var(--text-subtle)]">
                    <X className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="line-through opacity-60">{f}</span>
                  </li>
                ))}
              </ul>

              {plan.tier !== 'free' && (
                <div className="space-y-2">
                  {selectedTier === plan.tier ? (
                    <>
                      <button
                        onClick={() => handleUpgrade(plan.tier, 'stripe')}
                        disabled={!!loadingTier}
                        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-lg)] bg-[var(--accent)] py-2.5 font-medium text-[var(--accent-text)] transition-all hover:opacity-90 disabled:opacity-40"
                        aria-busy={isLoading(plan.tier, 'stripe')}
                      >
                        {isLoading(plan.tier, 'stripe') ? (
                          'Loading…'
                        ) : (
                          <>
                            <CreditCard className="h-4 w-4" />
                            Pay with Card
                          </>
                        )}
                      </button>
                      {/* Payment method badges */}
                      <div className="flex items-center justify-center gap-2 text-[length:var(--text-2xs)] text-[var(--text-subtle)]">
                        <span className="rounded border border-[var(--border)] px-1.5 py-0.5">Visa</span>
                        <span className="rounded border border-[var(--border)] px-1.5 py-0.5">Mastercard</span>
                        <span className="rounded border border-[var(--border)] px-1.5 py-0.5">Apple Pay</span>
                        <span className="rounded border border-[var(--border)] px-1.5 py-0.5">Google Pay</span>
                      </div>
                      <button
                        onClick={() => handleUpgrade(plan.tier, 'paypal')}
                        disabled={!!loadingTier}
                        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] py-2.5 font-medium text-[var(--text)] transition-all hover:bg-[var(--surface-3)] disabled:opacity-40"
                        aria-busy={isLoading(plan.tier, 'paypal')}
                      >
                        {isLoading(plan.tier, 'paypal') ? (
                          'Loading…'
                        ) : (
                          <>
                            {/* PayPal icon SVG */}
                            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M7.076 21.337H2.47a.641.641 0 0 1-.633-.74L4.944.901C5.026.382 5.474 0 5.998 0h7.46c2.57 0 4.578.543 5.69 1.81 1.01 1.15 1.304 2.42 1.012 4.287-.023.143-.047.288-.077.437-.983 5.05-4.349 6.797-8.647 6.797h-2.19c-.524 0-.968.382-1.05.9l-1.12 7.106zm14.146-14.42a3.35 3.35 0 0 0-.607-.541c-1.027-.707-2.503-1.023-4.19-1.023h-5.533c-.468 0-.868.334-.94.8l-1.828 11.597a.493.493 0 0 0 .488.572h3.968c.34 0 .63-.246.687-.583l.404-2.56a.684.684 0 0 1 .687-.583h1.737c3.62 0 5.958-1.758 6.723-5.445.317-1.575.154-2.89-.596-3.834z" />
                            </svg>
                            PayPal
                          </>
                        )}
                      </button>
                      <button
                        onClick={() => setSelectedTier(null)}
                        className="w-full py-1 text-xs text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setSelectedTier(plan.tier)}
                      disabled={!!loadingTier}
                      className={`w-full rounded-[var(--radius-lg)] py-2.5 font-medium transition-all disabled:opacity-40 ${
                        plan.highlighted
                          ? 'bg-[var(--accent)] text-[var(--accent-text)] hover:opacity-90'
                          : 'border border-[var(--border)] bg-[var(--surface-2)] text-[var(--text)] hover:bg-[var(--surface-3)]'
                      }`}
                    >
                      Upgrade
                    </button>
                  )}
                </div>
              )}
              {plan.tier === 'free' && (
                <button
                  disabled
                  className="w-full cursor-default rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] py-2.5 font-medium text-[var(--text-muted)]"
                >
                  Current Plan
                </button>
              )}
            </SpotlightCard>
          ))}
        </div>

        {/* Enterprise — custom terms, not a fixed self-serve price */}
        <div className="mx-auto mt-8 max-w-3xl rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface)] px-6 py-4 text-center">
          <p className="text-sm text-[var(--text)]">
            <span className="font-semibold">Need more than Pro?</span>{' '}
            <span className="text-[var(--text-muted)]">
              Custom model integrations, self-hosted deployment, SLAs, and volume pricing.
            </span>
          </p>
          <Link
            href="/contact?topic=enterprise"
            className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--accent)] hover:underline"
          >
            <Mail className="h-4 w-4" />
            Contact us for Enterprise
          </Link>
        </div>

        {/* Trust badges */}
        <div className="mt-12 flex flex-wrap items-center justify-center gap-6 text-xs text-[var(--text-subtle)]">
          <div className="flex items-center gap-1.5">
            <Shield className="h-4 w-4" />
            <span>Secure checkout (Stripe &amp; PayPal)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CreditCard className="h-4 w-4" />
            <span>Cancel anytime</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="h-4 w-4" />
            <span>14-day money-back guarantee</span>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
