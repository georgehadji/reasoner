import Link from 'next/link';
import { DisagreementField } from '@/components/landing/DisagreementField';
import { Aside, Body, Heading, Lede, Section } from '@/components/landing/prose';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { LogoLoop } from '@/components/ui/LogoLoop';
import { CAPABILITIES, MARQUEE_LABS } from '@/lib/capabilities.generated';
import { CLAIM_SPECIMENS } from '@/lib/demo-record';

/**
 * The home page, positioned for buyers who have to defend an answer to
 * someone else: regulated, high-stakes, audited. The claim is not "better
 * answers"; it is that the reasoning behind an answer can be checked.
 *
 * Order: the claim → the four things an auditor can check → which labs see
 * the question (Western-only) → six sectors → how a pilot runs → the site's
 * own claims, labelled the way the product labels its output → integrations
 * → an index of the other capabilities → close.
 *
 * Copy discipline, binding:
 * - Every product fact here is checkable in the repo. The source for each is
 *   in the comment beside it.
 * - No accuracy, safety, compliance or customer claim. Anything not yet true
 *   or not yet known is said so, in the "Our own claims" section, rather
 *   than left out.
 * - Sector rows describe uses and name the methods that serve them. They do
 *   not imply anyone in that sector uses Reasoner.
 * - Healthcare is operational only. Anything that informs diagnosis or
 *   treatment can be a medical device under EU MDR / FDA rules.
 */

/* ── Content ────────────────────────────────────────────── */

/**
 * Where each marquee lab is headquartered. An unmapped lab renders as a bare
 * name: a missing origin is a gap, a guessed one is a false claim.
 */
const LAB_ORIGIN: Readonly<Record<string, string>> = {
  Anthropic: 'US',
  OpenAI: 'US',
  Google: 'US',
  Mistral: 'FR',
  DeepSeek: 'CN',
  xAI: 'US',
  Perplexity: 'US',
  Qwen: 'CN',
  'Moonshot AI': 'CN',
  Meta: 'US',
  'Zhipu AI': 'CN',
  MiniMax: 'CN',
};

/**
 * The four things an auditor can check. Sources:
 * - labels: synthesis contract, PRODUCT.md "Epistemic labeling";
 * - labs: Phase 2 cross-lab validator + test, and generators blind to each
 *   other (CLAUDE.md, propagation resistance);
 * - critic: Phase 3 score fields (logical_consistency, evidence_support,
 *   failure_resilience, feasibility, bias_flags, steel_man) in demo-run.json;
 * - record: the SQLite event store (infrastructure/persistence).
 */
const AUDIT_POINTS = [
  {
    term: 'Every claim is labelled',
    detail:
      'Verified, hypothesis or unknown, by rule rather than by asking a model how sure it feels. The answer cannot present a guess as a fact.',
  },
  {
    term: 'Several labs answer, blind to each other',
    detail:
      'At least three labs on Budget presets and four on Premium, enforced in code. No answer sees another before it is written, so one lab’s blind spot cannot set the result.',
  },
  {
    term: 'A separate critic scores them',
    detail:
      'Each answer is scored for logical consistency, evidence, resilience to failure and feasibility, by a model from outside the dominant lab. Rejected positions stay on the record in their strongest form.',
  },
  {
    term: 'The run stays on the record',
    detail:
      'Each run is stored as a log of events: every phase, which model wrote it, and what the critic scored. Whoever signs off can read how the answer was built.',
  },
];

/**
 * Sector rows. Methods are real `method` values in preset_registry.py.
 * `limit` is the boundary stated up front, which is what a regulated reader
 * looks for first.
 */
const SECTORS = [
  {
    name: 'Defence and security',
    use: 'Structured adversarial analysis of plans: red-team a course of action, or run a pre-mortem on why it failed.',
    methods: 'Debate · Pre-Mortem · Dialectical, on Western-only routing',
    limit: 'Analysis for the people who decide. It does not decide.',
  },
  {
    name: 'Healthcare operations',
    use: 'Staffing, procurement and incident root-cause analysis. Morbidity and mortality reviews as pre-mortem or Socratic questioning. Comparing guidelines with cited sources.',
    methods: 'Pre-Mortem · Socratic · Research',
    limit: 'Not for diagnosis or treatment decisions. Do not enter patient data.',
  },
  {
    name: 'Research and teaching',
    use: 'Research design and peer-review support: generate hypotheses and try to disprove them, update beliefs on evidence, teach critical thinking by questioning.',
    methods: 'Scientific · Bayesian · Socratic · Research',
    limit: 'A reviewer’s second reader, not a replacement for one.',
  },
  {
    name: 'Legal and compliance',
    use: 'Stress-test an argument against opposing counsel’s likely positions, run a pre-mortem on contract risk, and look for gaps against a regulation.',
    methods: 'Debate · Jury · Pre-Mortem',
    limit: 'Not legal advice.',
  },
  {
    name: 'Aerospace and engineering',
    use: 'Design reviews, failure-mode analysis in the style of an FMEA, and critique of requirements before they are frozen.',
    methods: 'Pre-Mortem · Iterative Critique',
    limit: 'Does not replace certified safety analysis.',
  },
  {
    name: 'Government and policy',
    use: 'Policy options analysis, structured expert consensus, and stress-testing scenarios before they are published.',
    methods: 'Delphi · Dialectical',
    limit: 'Options and their weaknesses, not a recommendation to adopt.',
  },
];

/** A pilot, as the owner has defined one: paid, four to six weeks, one named
 *  problem, measured against a human baseline. */
const PILOT_STEPS = [
  {
    term: 'One named problem',
    detail: 'A decision your team would otherwise review by hand.',
  },
  {
    term: 'A human baseline',
    detail: 'Your team’s own analysis of the same problem, done the usual way.',
  },
  {
    term: 'Routing you choose',
    detail: 'Western-only if you need it, and the labs used listed in advance.',
  },
  {
    term: 'Scored against the baseline',
    detail: 'What the run found that the baseline missed, and what it missed that the baseline found.',
  },
];

/**
 * The site's own claims, labelled the way the product labels its output.
 * VERIFIED rows each name the place in the repo that makes them true.
 */
const OWN_CLAIMS = [
  {
    label: 'VERIFIED',
    claim: 'Cross-lab routing is enforced by a validator and a test, not by prompt wording.',
  },
  {
    label: 'VERIFIED',
    claim:
      'Every preset has a Western-only twin that uses only US and EU models. When it is on, the provider builder refuses any model from another bloc.',
  },
  {
    label: 'VERIFIED',
    claim:
      'One call erases a user’s stored data. The code is source-available under a Business Source License that converts to Apache-2.0 in 2030, and runs self-hosted as a Docker stack.',
  },
  {
    label: 'HYPOTHESIS',
    claim:
      'That cross-lab critique gives better-calibrated answers than a single model. The benchmark harness exists; results are not published yet.',
  },
  {
    label: 'UNKNOWN',
    claim:
      'Air-gapped deployment. Local models run through Ollama, but there is no documented setup that works with no connection to OpenRouter.',
  },
  {
    label: 'UNKNOWN',
    claim: 'Data residency. [INPUT REQUIRED: which regions data is stored and processed in]',
  },
  {
    label: 'UNKNOWN',
    claim:
      'Patient-data agreements. [INPUT REQUIRED: is there a HIPAA BAA or GDPR data-processing agreement covering OpenRouter and every model provider?]',
  },
];

/** The three driving adapters (api/mcp/tools.py, api/routes/agent.py,
 *  main.py + reasoner.headless.ask). */
const AGENT_DOORS = [
  {
    name: 'MCP',
    detail: 'Six tools, one config block. Claude Desktop, Claude Code and most agent frameworks pick it up.',
  },
  {
    name: 'HTTP and TypeScript SDK',
    detail: 'One authenticated POST, or the SDK. Take the result as JSON, or stream the phases as they land.',
  },
  {
    name: 'CLI',
    detail: 'A shell or a cron job, or the pipeline imported in-process with no server in between.',
  },
];

/** Fill AND rule pattern carry the label (globals.css .epistemic-*). */
const CLAIM_RULE: Record<string, string> = {
  VERIFIED: 'epistemic-verified',
  HYPOTHESIS: 'epistemic-hypothesis',
  UNKNOWN: 'epistemic-unknown',
};

const INLINE_LINK =
  'link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]';
const PRIMARY_CTA =
  'btn-lift group flex min-h-[var(--space-12)] items-center gap-[var(--space-2)] rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]';
const SECONDARY_CTA =
  'link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[length:var(--text-md)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]';
const TERM =
  'font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]';
const DETAIL =
  'mt-[var(--space-1)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]';
const LABEL_TAG =
  'pl-[var(--space-3)] font-sans text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]';

function PilotCta() {
  return (
    <Link href="/contact?topic=pilot" className={PRIMARY_CTA}>
      Scope a pilot
      <span
        aria-hidden="true"
        className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
      >
        &rarr;
      </span>
    </Link>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div className="min-h-dvh bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead ─────────────────────────────────────────── */}
        <header className="relative mx-auto flex min-h-svh w-full max-w-[var(--width-wide)] flex-col justify-center px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-48)]">
          <DisagreementField />

          <div className="relative grid gap-[var(--space-12)] lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-start lg:gap-[var(--space-16)]">
            <h1 className="max-w-[16ch] text-balance font-display text-[length:var(--text-6xl)] font-normal leading-[var(--lh-display)] lg:text-[length:var(--text-7xl)] tracking-[var(--tracking-tight)] text-[var(--text)]">
              Answers with the working shown.
            </h1>

            <div className="lg:self-end">
              <p className="prose-measure text-[length:var(--text-2xl)] leading-[1.6] text-[var(--text-2)]">
                Reasoner puts a hard question to models from several AI labs, has a separate model
                critique their answers, and labels every claim{' '}
                <strong className="font-medium text-[var(--text)]">
                  verified, hypothesis or unknown.
                </strong>{' '}
                The whole run stays on the record, so whoever has to sign off can see how the answer
                was built.
              </p>
            </div>
          </div>

          <div className="relative mt-[var(--space-12)] flex flex-wrap items-center gap-[var(--space-3)] gap-x-[var(--space-8)]">
            <PilotCta />
            {/* A sceptic converts on evidence they can read alone. */}
            <Link href="/how-it-works" className={SECONDARY_CTA}>
              Read a complete run
            </Link>
          </div>
        </header>

        {/* ── What an auditor can check ───────────────────────── */}
        <Section tone="invert" id="audit">
          <Heading>Four things you can check before you trust it.</Heading>
          <Lede>
            A regulated decision is judged on why the answer can be trusted, not only on the
            answer. Every Reasoner run leaves four things behind for that.
          </Lede>

          <dl className="mt-[var(--space-10)] grid gap-x-[var(--space-8)] gap-y-[var(--space-8)] sm:grid-cols-2">
            {AUDIT_POINTS.map(({ term, detail }) => (
              <div key={term} className="border-t border-[var(--border-strong)] pt-[var(--space-4)]">
                <dt className={TERM}>{term}</dt>
                <dd className={DETAIL}>{detail}</dd>
              </div>
            ))}
          </dl>

          <Body>
            Three claims from{' '}
            <Link href="/how-it-works" className={INLINE_LINK}>
              one captured run
            </Link>
            , with the labelling untouched:
          </Body>

          {/* Real output, derived from the captured run, never transcribed. */}
          <dl className="mt-[var(--space-6)] space-y-[var(--space-5)]">
            {CLAIM_SPECIMENS.map(({ claim, label, qualifier }) => (
              <div key={label} className="border-t border-[var(--border)] pt-[var(--space-4)]">
                <dt className={`${CLAIM_RULE[label]} ${LABEL_TAG}`}>
                  {label}
                  {qualifier ? (
                    <span className="font-normal normal-case tracking-normal text-[var(--text-subtle)]">
                      {' '}
                      {qualifier}
                    </span>
                  ) : null}
                </dt>
                <dd className="prose-measure mt-[var(--space-2)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {claim}
                </dd>
              </div>
            ))}
          </dl>

          <Aside href="/capabilities">How each check works &rarr;</Aside>
        </Section>

        {/* ── Which labs see the question ─────────────────────────
            Western-only: domain/preset_registry_western.py (49 twins,
            tests/unit/test_preset_western.py), enforced by
            core/model_policy.restrict_blocs() at registry.build_provider(),
            and the Composer's "Western" toggle (auto-western-<tier>). */}
        <Section id="labs">
          <Heading>You choose which labs see the question.</Heading>
          <Lede>
            By default a run draws on labs in rival geopolitical blocs, so no single one sets the
            answer. Where that is not acceptable, switch to Western-only: every preset has a twin
            that uses only US and EU models, and the run refuses any other model rather than
            falling back to one.
          </Lede>

          <div className="mt-[var(--space-10)]">
            <LogoLoop
              ariaLabel="Model labs Reasoner routes to, with the country each lab is based in"
              items={MARQUEE_LABS.map((name) => (
                <span key={name} className="flex items-baseline gap-[var(--space-2)]">
                  <span className="font-sans text-[length:var(--text-md)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)]">
                    {name}
                  </span>
                  {LAB_ORIGIN[name] ? (
                    <span className="font-sans text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                      {LAB_ORIGIN[name]}
                    </span>
                  ) : null}
                </span>
              ))}
            />
          </div>

          <Body>
            The restriction is set once per run and checked where every model provider is built,
            including when a model fails and the run falls back to another. The providers a run
            can reach are listed in{' '}
            <Link href="/subprocessors" className={INLINE_LINK}>
              sub-processors
            </Link>
            .
          </Body>
        </Section>

        {/* ── Sectors ──────────────────────────────────────────── */}
        <Section id="sectors">
          <Heading>Where a confident wrong answer costs the most.</Heading>
          <Lede>
            Six places it fits, the methods that serve each, and the line it does not cross. The
            method is chosen per question automatically; these are the ones each kind of question
            tends to get.
          </Lede>

          <dl className="mt-[var(--space-10)] divide-y divide-[var(--border)] border-y border-[var(--border)]">
            {SECTORS.map(({ name, use, methods, limit }) => (
              <div
                key={name}
                className="grid gap-[var(--space-2)] py-[var(--space-6)] lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)] lg:gap-[var(--space-8)]"
              >
                <dt className="font-display text-[length:var(--text-xl)] font-semibold leading-[var(--lh-heading)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="min-w-0">
                  <p className="prose-measure text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                    {use}
                  </p>
                  <p className="mt-[var(--space-2)] font-mono text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
                    {methods}
                  </p>
                  <p className="mt-[var(--space-2)] text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                    {limit}
                  </p>
                </dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* ── Pilot ────────────────────────────────────────────── */}
        <Section id="pilot" tone="invert">
          <Heading>Start with one problem, not a contract.</Heading>
          <Lede>
            A paid pilot runs four to six weeks on one problem you name, and is judged against
            your own team&rsquo;s analysis of it.
          </Lede>

          <ol className="mt-[var(--space-10)] grid list-none gap-x-[var(--space-8)] gap-y-[var(--space-6)] sm:grid-cols-2 lg:grid-cols-4">
            {PILOT_STEPS.map(({ term, detail }) => (
              <li key={term} className="border-t border-[var(--border-strong)] pt-[var(--space-4)]">
                <p className={TERM}>{term}</p>
                <p className={DETAIL}>{detail}</p>
              </li>
            ))}
          </ol>

          <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-4)]">
            <PilotCta />
          </div>
        </Section>

        {/* ── Own claims, labelled ─────────────────────────────── */}
        <Section id="claims">
          <Heading>Our own claims, labelled the same way.</Heading>
          <Lede>
            If the product will not present a guess as a fact, neither should the page selling it.
            What is true in the code today, what is not shown yet, and what is still open.
          </Lede>

          <dl className="mt-[var(--space-10)] space-y-[var(--space-5)]">
            {OWN_CLAIMS.map(({ label, claim }) => (
              <div key={claim} className="border-t border-[var(--border)] pt-[var(--space-4)]">
                <dt className={`${CLAIM_RULE[label]} ${LABEL_TAG}`}>{label}</dt>
                <dd className="prose-measure mt-[var(--space-2)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                  {claim}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            No accuracy, safety or compliance certification is claimed. Full detail in{' '}
            <Link href="/security" className={INLINE_LINK}>
              security
            </Link>{' '}
            and{' '}
            <Link href="/privacy" className={INLINE_LINK}>
              privacy
            </Link>
            .
          </Body>
        </Section>

        {/* ── Integrations ─────────────────────────────────────── */}
        <Section id="agents">
          <Heading>It fits inside the tools you already use.</Heading>
          <Lede>
            The answer arrives as fields, not prose: the claims and their labels, the questions the
            run could not close, and a plan whose every step says how you will know it worked.
          </Lede>

          <dl className="mt-[var(--space-10)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-3">
            {AGENT_DOORS.map(({ name, detail }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className={TERM}>{name}</dt>
                <dd className={DETAIL}>{detail}</dd>
              </div>
            ))}
          </dl>

          <Body>
            Three doors, one pipeline and one ledger. Setup for an agent host is one dependency and
            a config block:{' '}
            <Link href="/docs/mcp" className={INLINE_LINK}>
              add the MCP server
            </Link>
            .
          </Body>

          <Aside href="/developers">The developer surface, in full &rarr;</Aside>
        </Section>

        {/* ── Everything else ──────────────────────────────────── */}
        <Section id="more">
          <Body>
            The same pipeline also runs {CAPABILITIES.methods} reasoning methods in all, including
            long-form writing that passes through nine phases on different models,{' '}
            <Link href="/capabilities#image-making" className={INLINE_LINK}>
              image generation across labs
            </Link>
            , brainstorming, and code that one lab writes and another attacks. See{' '}
            <Link href="/capabilities" className={INLINE_LINK}>
              capabilities
            </Link>
            .
          </Body>
        </Section>

        {/* ── Close ────────────────────────────────────────────── */}
        <Section>
          <Heading>Bring one problem you would check by hand.</Heading>
          <Lede>
            The kind where being confidently wrong would cost you. That is the case this was built
            for.
          </Lede>
          <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-4)] gap-x-[var(--space-8)]">
            <PilotCta />
            <Link href="/chat" className={SECONDARY_CTA}>
              Or ask a question now
            </Link>
          </div>
        </Section>
      </main>

      <SiteFooter />
    </div>
  );
}
