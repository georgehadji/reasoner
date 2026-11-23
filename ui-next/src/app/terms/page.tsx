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
  ROW,
} from '@/components/site/ArgumentSection';
import { EPISTEMIC_TAG, epistemicClassName, type EpistemicLabelName } from '@/lib/remark-epistemic';
import { SITE } from '@/lib/site';

/**
 * /terms in the site world "The product performs".
 *
 * The section text is the terms; the hero list is only a summary of it, and
 * says so. The wording is the previous page's, changed only where it was
 * false: "Last updated" printed today's date on every visit; "99.9% uptime"
 * had no measurement behind it (/status publishes no uptime history); and a
 * ban on reverse-engineering contradicted the source being published under
 * the Business Source Licence, whose one restriction now stands in its place.
 * Jurisdiction and effective date are the owner's to state. No new terms
 * were drafted here.
 */

const BRIEF = [
  { n: 1, title: 'Acceptance', gist: 'Using Reasoner means agreeing to these terms.' },
  { n: 2, title: 'Ownership', gist: 'You own your inputs and outputs.' },
  { n: 3, title: 'Accuracy', gist: 'AI output can be wrong; verify what matters.' },
  { n: 4, title: 'Prohibited uses', gist: 'No harm, no bypassing limits, no resale as a service.' },
  { n: 5, title: 'Availability', gist: 'Provided as is; accounts can be suspended.' },
  { n: 6, title: 'Governing law', gist: 'Jurisdiction to be stated.' },
];

/** From the parameters block of LICENSE at the repository root. */
const LICENCE = [
  { term: 'Licence', value: 'Business Source License 1.1' },
  { term: 'Licensor', value: 'Polytonic' },
  { term: 'You may', value: 'Use, modify and self-host it for your own internal or personal purposes' },
  { term: 'You may not', value: 'Offer it, or a substantially similar work, to others as a hosted service' },
  { term: 'Changes to', value: 'Apache License 2.0 on 17 August 2030' },
];

const LABELS: Array<{ label: EpistemicLabelName; meaning: string }> = [
  { label: 'VERIFIED', meaning: 'Backed by a source outside the model: a search result, your document, a check that ran.' },
  { label: 'HYPOTHESIS', meaning: 'Reasoned, but nothing outside the model confirms it.' },
  { label: 'UNKNOWN', meaning: 'The evidence available does not settle it.' },
];

const PROHIBITED = [
  'Generate illegal or harmful content.',
  'Exceed assigned rate limits or bypass security controls.',
  'Use automated systems to scrape or extract data without authorisation.',
  'Offer Reasoner, or a substantially similar service, to third parties as a hosted service.',
];

const FOOT = 'border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]';

export default function TermsPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Hero: the page (left), the terms in brief (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Terms of</span>
              </span>
              <span className="site-line">
                <span>service.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                The agreement between you and {SITE.legalName} when you use {SITE.name}: six sections, each
                short.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <a href="#acceptance" className="site-button">
                  Read the terms
                </a>
                <Link href="/privacy" className={`site-link ${BODY}`}>
                  Read the privacy policy
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <nav
              data-ui
              aria-label="The terms in brief"
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <p className={CAP}>In brief. The sections below are the terms.</p>
              <ol className="list-none">
                {BRIEF.map(({ n, title, gist }) => (
                  <li key={n} className={`grid grid-cols-[auto_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold nums-tabular">{n}</span>
                    <span>
                      <span className="font-semibold">{title}.</span>{' '}
                      <span className="text-[var(--site-muted)]">{gist}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </nav>
          </div>
        </header>

        <Section id="acceptance" lines={['1. Accepting', 'these terms.']}>
          <Body>
            By accessing or using the Reasoner platform, you agree to be bound by these Terms of Service
            and all applicable laws and regulations. If you do not agree with any of these terms, you are
            prohibited from using or accessing this site.
          </Body>
        </Section>

        <Section
          id="ownership"
          lines={['2. You own', 'what you make.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>The source licence, from the repository</figcaption>
              <dl>
                {LICENCE.map(({ term, value }) => (
                  <div key={term} className={`grid grid-cols-[minmax(0,2fr)_minmax(0,5fr)] gap-[var(--space-3)] ${ROW}`}>
                    <dt className="text-[var(--site-muted)]">{term}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            Permission is granted to access and use the Reasoner reasoning engine for professional,
            educational, or research purposes.
          </Body>
          <Body>
            <strong className="font-semibold">Data ownership:</strong> notwithstanding anything to the
            contrary, you retain full ownership and intellectual property rights over all inputs and
            outputs processed through the system. Reasoner claims no ownership over your proprietary
            reasoning processes.
          </Body>
        </Section>

        <Section
          id="accuracy"
          lines={['3. AI output', 'can be wrong.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>What each label on an answer means</figcaption>
              <ul className="list-none">
                {LABELS.map(({ label, meaning }) => (
                  <li key={label} className={ROW}>
                    <span className={epistemicClassName(EPISTEMIC_TAG[label])}>{label}</span>
                    <p className="mt-[var(--space-1)]">{meaning}</p>
                  </li>
                ))}
              </ul>
              <p className={FOOT}>A label describes the evidence behind a claim, not whether the claim is true.</p>
            </figure>
          }
        >
          <Body>
            Reasoner uses artificial intelligence. AI-generated content can contain inaccuracies,
            hallucinations, or biases. The system is designed to provide structured reasoning and
            verification, but you must independently verify all critical outputs. Reasoner is a tool for
            thought, not a replacement for professional judgment.
          </Body>
        </Section>

        <Section
          id="prohibited"
          lines={['4. What you', 'may not do.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>You agree not to use the platform to</figcaption>
              <ol className="list-none">
                {PROHIBITED.map((item, i) => (
                  <li key={item} className={`grid grid-cols-[auto_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold nums-tabular">{String.fromCharCode(97 + i)}</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ol>
            </figure>
          }
        >
          <Body>
            You agree not to use the platform for any of the purposes listed. The last restates the one
            restriction of the source licence; reading, modifying and self-hosting the code for your own
            use is permitted by it.
          </Body>
        </Section>

        <Section id="availability" lines={['5. Availability', 'and suspension.']}>
          <Body>
            Reasoner is provided &ldquo;as is&rdquo;. We reserve the right to modify or discontinue the service
            with reasonable notice to enterprise customers. We may suspend accounts that violate our
            security policies or these terms.
          </Body>
          <Body>
            Current service health is on the{' '}
            <Link href="/status" className="site-link">
              status page
            </Link>
            .
          </Body>
        </Section>

        <Section id="law" lines={['6. Governing', 'law.']} field>
          <Body>
            These terms shall be governed by and construed in accordance with the laws of [INPUT REQUIRED:
            governing jurisdiction and courts], without regard to its conflict of law provisions.
          </Body>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">A question about</span>
            <span className="block">these terms?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            {SITE.name} is operated by {SITE.legalName}. Ask before you rely on a reading of them.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/contact" className="site-button">
              Get in touch
            </Link>
          </div>
          <p className={`mt-[var(--space-12)] text-[var(--site-muted)] ${BODY}`}>
            Effective [INPUT REQUIRED: effective date of these terms].
          </p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
