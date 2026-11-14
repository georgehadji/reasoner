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
import { MODEL_VENDORS, PROVIDERS } from '@/lib/capabilities.generated';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Sub-processors',
  description:
    'Every outside service a Reasoner run can send data to, and what each receives. Model makers are generated from the routing registry.',
  alternates: { canonical: absoluteUrl('/subprocessors') },
};

/**
 * /subprocessors in the site world "The product performs".
 *
 * Corrected 2026-11-14: the page said its list "cannot go stale", but it
 * named only the eight direct fallback adapters. Every run goes through
 * OpenRouter first, the registry reaches some thirty model makers through
 * it, and search, sign-in, payments, email and error reporting were not
 * listed at all. The makers now come from MODEL_VENDORS, generated from the
 * same registry by scripts/update_mindmap_meta.py.
 */

/** One run, in the order its data leaves our servers. */
const PATH = [
  { to: 'OpenRouter', gets: 'Your question and the context the run includes, on every model call' },
  { to: 'The model’s host', gets: 'The same, passed on by OpenRouter for the models the run uses' },
  { to: 'Brave or Tavily', gets: 'Search queries written from your question, when the run searches' },
  { to: 'Sentry', gets: 'An error report, which can include the failed request' },
];

/**
 * Root privacy pages only: deep links to a DPA subpage go stale silently.
 * Keyed to PROVIDERS, the direct fallback adapters.
 */
const PRIVACY_POLICY: Record<string, string> = {
  Anthropic: 'https://www.anthropic.com/legal/privacy',
  OpenAI: 'https://openai.com/policies/privacy-policy',
  Google: 'https://policies.google.com/privacy',
  Mistral: 'https://mistral.ai/terms/#privacy-policy',
  DeepSeek: 'https://www.deepseek.com/en/privacy-policy',
  xAI: 'https://x.ai/legal/privacy-policy',
  Perplexity: 'https://www.perplexity.ai/hub/legal/privacy-policy',
  Qwen: 'https://qwen.ai/privacy',
};

/** Services outside the model call, each from its adapter in the code. */
const SERVICES = [
  { name: 'Brave Search, Tavily', role: 'Web search', gets: 'Search queries written from your question' },
  { name: 'Supabase', role: 'Sign-in', gets: 'Your email address and sign-in session' },
  { name: 'Stripe, PayPal', role: 'Payments', gets: 'Card or account details, entered on their own pages' },
  { name: 'Resend', role: 'Email', gets: 'What you write in the contact form, and your address' },
  { name: 'Sentry', role: 'Error reports', gets: 'Reports of failures, and page performance traces' },
];

function host(url: string): string {
  return url.replace(/^https?:\/\//, '').split('/')[0];
}

export default function SubprocessorsPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), one run's path out (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Who else sees</span>
              </span>
              <span className="site-line">
                <span>your request.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Every outside service a run can send data to, and what each one receives. The model makers
                are generated from the registry the pipeline routes through.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <a href="#models" className="site-button">
                  See every model maker
                </a>
                <Link href="/privacy" className={`site-link ${BODY}`}>
                  Read the privacy policy
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>One run, as its data leaves our servers</figcaption>
              <ol className="list-none">
                {PATH.map(({ to, gets }, i) => (
                  <li key={to} className={`grid grid-cols-[auto_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold nums-tabular">{i + 1}</span>
                    <span>
                      <span className="font-semibold">{to}.</span>{' '}
                      <span className="text-[var(--site-muted)]">{gets}.</span>
                    </span>
                  </li>
                ))}
              </ol>
            </figure>
          </div>
        </header>

        <Section
          id="models"
          lines={['Every model maker', 'a run can reach.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>
                {MODEL_VENDORS.length} makers, by their OpenRouter name, from the registry
              </figcaption>
              <ul className="grid list-none grid-cols-2 gap-x-[var(--space-4)] px-[var(--space-4)] py-[var(--space-4)] sm:grid-cols-3">
                {MODEL_VENDORS.map((slug) => (
                  <li key={slug} className="py-[var(--space-1)]">
                    <code className="font-mono">{slug}</code>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            Every model call goes to OpenRouter, which passes it to a host serving the chosen model. A run
            reaches only the models its preset names, never all of these at once.
          </Body>
          <Body>
            For open-weight models, OpenRouter may choose a host other than the maker, and we do not pin it.
            [INPUT REQUIRED: whether to pin OpenRouter hosts or require a no-training data policy.]
          </Body>
          <Body>Models you run locally through Ollama send nothing out and are not listed.</Body>
        </Section>

        <Section
          id="fallback"
          lines={['When OpenRouter', 'does not answer.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Direct fallbacks, with each maker&rsquo;s privacy policy</figcaption>
              <ul className="list-none">
                {PROVIDERS.map((name) => (
                  <li key={name} className={`grid grid-cols-[minmax(0,1fr)_auto] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold">{name}</span>
                    {PRIVACY_POLICY[name] ? (
                      <a
                        href={PRIVACY_POLICY[name]}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="site-link text-current"
                      >
                        {host(PRIVACY_POLICY[name])}
                      </a>
                    ) : (
                      <span>Not linked</span>
                    )}
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            If OpenRouter fails, the call can go straight to the maker&rsquo;s own API instead. These are the
            makers with a direct adapter; the request they receive is the same.
          </Body>
          <Body>
            A Western-only run is restricted to US and EU makers at one point in the code, so neither route can
            reach any other.
          </Body>
        </Section>

        <Section
          id="services"
          lines={['Around the', 'model call.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Other services, and what each receives</figcaption>
              <ul className="list-none">
                {SERVICES.map(({ name, role, gets }) => (
                  <li key={name} className={ROW}>
                    <p className="flex flex-wrap items-baseline justify-between gap-x-[var(--space-3)]">
                      <span className="font-semibold">{name}</span>
                      <span className="text-[var(--site-muted)]">{role}</span>
                    </p>
                    <p className="mt-[var(--space-1)]">{gets}.</p>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            Each is called only when its key is configured on the server. Stripe and PayPal take payment on
            their own pages; we keep only their customer and subscription IDs.
          </Body>
          <Body>
            The API, its database and its cache run on [INPUT REQUIRED: hosting provider and region for the
            API, database and cache].
          </Body>
          <More href="/cookies">What stays in your browser</More>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">A service missing</span>
            <span className="block">from this list?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            Tell us what you saw your data reach. If this page missed it, the page is wrong and we will fix it.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/contact" className="site-button">
              Get in touch
            </Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
