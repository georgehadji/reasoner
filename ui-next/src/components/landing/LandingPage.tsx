import Link from 'next/link';
import { Logo } from '@/components/brand/Logo';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CommandList } from '@/components/site/CommandList';
import { CritiqueSplit } from '@/components/site/CritiqueSplit';
import { HeroRecord } from '@/components/site/HeroRecord';
import { LabBoard } from '@/components/site/LabBoard';
import { PilotDialog } from '@/components/site/PilotDialog';
import { PilotPinned } from '@/components/site/PilotPinned';
import { Reveal } from '@/components/site/Reveal';
import { ReviewAgenda } from '@/components/site/ReviewAgenda';

/**
 * The home page, in the site world "The product performs"
 * (spec/art-direction.md). Idea: on this page, one real run record
 * becomes the working fragments the visitor handles: its labels switch
 * on and off, its critic's score sheet answers the pointer, its routing
 * refuses labs when Western-only is on.
 *
 * Argument, one section per claim:
 *   hero      answers a reviewer can check (proof: a real synthesis, labels on/off)
 *   critique  several labs answer blind, a separate critic scores them (real scores)
 *   labs      you choose which labs see it (Western-only, enforced in code)
 *   sectors   each reviewer's first questions, answered with a status
 *   pilot     how a pilot runs (paid, 4-6 weeks, judged against your team)
 *   commands  what it does, by name (MCP, HTTP, CLI, self-host, erase)
 *   claims    the page's own claims, labelled the way the product labels
 *   start     propose a pilot
 *
 * Copy discipline, binding: every product fact is checkable in the repo;
 * no accuracy, safety, compliance or customer claim; anything not known is
 * said so in "Our own claims". Healthcare is operational only.
 */

/** The site's own claims, labelled the way the product labels its output.
 *  Verified rows each rest on code: the cross-lab validator and its test,
 *  domain/preset_registry_western.py + restrict_blocs(), erase_user_data,
 *  LICENSE (BSL 1.1 → Apache-2.0 2030-08-17) and the compose file. */
const OWN_CLAIMS = [
  { label: 'Verified', rule: 'epistemic-verified', claim: 'Cross-lab routing is enforced by a validator and a test, not by prompt wording.' },
  { label: 'Verified', rule: 'epistemic-verified', claim: 'Every preset has a Western-only twin. When it is on, the provider builder refuses any model from another bloc.' },
  { label: 'Verified', rule: 'epistemic-verified', claim: 'One call erases a user’s stored data. The code is source-available, converts to Apache-2.0 in 2030, and runs self-hosted.' },
  { label: 'Hypothesis', rule: 'epistemic-hypothesis', claim: 'That cross-lab critique gives better-calibrated answers than a single model. The benchmark harness exists; results are not published yet.' },
  { label: 'Unknown', rule: 'epistemic-unknown', claim: 'Air-gapped deployment. Local models run through Ollama, but there is no documented setup with no connection to OpenRouter.' },
  { label: 'Unknown', rule: 'epistemic-unknown', claim: 'Data residency. [INPUT REQUIRED: which regions data is stored and processed in]' },
] as const;

export default function LandingPage() {
  return (
    <div className="site min-h-dvh">
      <Reveal />

      <main id="main-content">
        {/* ── Hero: control that reads the page ───────────────────── */}
        <header className="relative grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <Link href="/" aria-label="Reasoner home" className="absolute left-[var(--site-margin)] top-[var(--space-8)] z-10">
            <Logo showWordmark size={24} />
          </Link>
          <Link href="/chat" className="site-link absolute right-[var(--site-margin)] top-[var(--space-8)] text-[length:var(--site-small)]">
            Open the app
          </Link>
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-24)] lg:pb-[var(--space-10)] lg:pt-[var(--space-12)]">
            <div>
              <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
                <span className="site-line">
                  <span>Answers you</span>
                </span>
                <span className="site-line">
                  <span>can check.</span>
                </span>
              </h1>
              <div className="site-after-headline">
                <p className="mt-[var(--space-8)] max-w-[44ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                  Reasoner puts a hard question to models from rival AI labs, has a separate model
                  critique them, and labels every claim verified, hypothesis or unknown. The whole run
                  stays on the record for whoever has to sign off.
                </p>
                <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                  <a href="#start" className="site-button">
                    Propose a pilot
                  </a>
                  <Link href="/how-it-works" className="site-link text-[length:var(--site-body)]">
                    Read a complete run
                  </Link>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-10)]">
            <HeroRecord />
          </div>
        </header>

        <CritiqueSplit />
        <LabBoard />
        <ReviewAgenda />
        <PilotPinned />
        <CommandList />

        {/* ── Own claims, labelled ─────────────────────────────── */}
        <section id="claims" aria-labelledby="claims-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <div className="grid gap-[var(--space-10)] lg:grid-cols-12">
            <div className="lg:col-span-4">
              <h2 id="claims-h" className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">
                Our own claims, labelled.
              </h2>
              <p className="mt-[var(--space-6)] max-w-[36ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
                If the product will not present a guess as a fact, neither should the page selling
                it. No accuracy, safety or compliance certification is claimed.
              </p>
            </div>
            <dl className="space-y-[var(--space-8)] lg:col-span-7 lg:col-start-6" data-reveal>
              {OWN_CLAIMS.map(({ label, rule, claim }) => (
                <div key={claim}>
                  <dt className={`${rule} pl-[var(--space-3)] text-[length:var(--site-small)] font-semibold`}>{label}</dt>
                  <dd className="mt-[var(--space-2)] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">{claim}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <PilotDialog />
      </main>

      <SiteFooter />
    </div>
  );
}
