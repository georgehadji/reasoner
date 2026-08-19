import type { Metadata } from 'next';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { PROVIDERS } from '@/lib/capabilities.generated';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Sub-processors',
  description:
    'The model providers Reasoner routes requests to, generated from the live provider registry.',
  alternates: { canonical: absoluteUrl('/subprocessors') },
};

/**
 * Privacy policy links, keyed to the live PROVIDERS list from
 * capabilities.generated.ts. Root-domain links only — deep-linking to a
 * specific DPA subpage risks going stale silently; a root privacy page does
 * not.
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

export default function SubprocessorsPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main className="mx-auto w-full max-w-[var(--width-content)] flex-1 px-[var(--gutter)] py-[var(--space-24)]">
        <header className="mb-[var(--space-12)] border-b border-[var(--border)] pb-[var(--space-12)]">
          <h1 className="font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)] md:text-[length:var(--text-5xl)]">
            Sub-processors
          </h1>
          <p className="prose-measure mt-[var(--space-4)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            To generate a response, Reasoner sends your request to one or more of the model
            providers below. This list is generated from the same provider registry the pipeline
            routes through, so it cannot go stale when routing changes.
          </p>
        </header>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[length:var(--text-sm)]">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="py-[var(--space-3)] pr-[var(--space-4)] font-sans font-semibold text-[var(--text)]">
                  Provider
                </th>
                <th className="py-[var(--space-3)] pr-[var(--space-4)] font-sans font-semibold text-[var(--text)]">
                  Purpose
                </th>
                <th className="py-[var(--space-3)] font-sans font-semibold text-[var(--text)]">
                  Privacy policy
                </th>
              </tr>
            </thead>
            <tbody>
              {PROVIDERS.map((name) => (
                <tr key={name} className="border-b border-[var(--border)]">
                  <td className="py-[var(--space-4)] pr-[var(--space-4)] font-medium text-[var(--text)]">
                    {name}
                  </td>
                  <td className="py-[var(--space-4)] pr-[var(--space-4)] text-[var(--text-muted)]">
                    Model inference on request content you submit.
                  </td>
                  <td className="py-[var(--space-4)]">
                    {PRIVACY_POLICY[name] ? (
                      <a
                        href={PRIVACY_POLICY[name]}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline hover:text-[var(--accent)]"
                      >
                        {PRIVACY_POLICY[name].replace(/^https?:\/\//, '').split('/')[0]}
                      </a>
                    ) : (
                      <span className="text-[var(--text-subtle)]">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="prose-measure mt-[var(--space-8)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
          This list reflects the providers configured in the pipeline&apos;s direct-adapter registry.
          Additional models are reachable via OpenRouter, which acts as a routing intermediary to
          the underlying provider. See{' '}
          <a href="/security" className="underline hover:text-[var(--accent)]">
            Security
          </a>{' '}
          for how requests are routed and encrypted.
        </p>
      </main>

      <SiteFooter />
    </div>
  );
}
