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
import { CAPABILITIES, SYCOPHANCY_CONTROLS } from '@/lib/capabilities.generated';
import { FREE_CREDITS } from '@/lib/credits';
import { EPISTEMIC_TAG, epistemicClassName, type EpistemicLabelName } from '@/lib/remark-epistemic';
import { SITE } from '@/lib/site';

/**
 * /about in the site world "The product performs": the home page's argument,
 * turned inward.
 *
 * A visitor who reaches an About page has read the feature copy and is here to
 * decide whether the people behind it can be trusted. So the page applies the
 * product's own rule to itself: its hero fragment is the page's claims, each
 * labelled with what it is, and the unfinished work is listed from the same
 * generated flags the build checks. Admitting unfinished work is load-bearing
 * here, not a disclaimer.
 *
 * Deliberately absent: an origin anecdote. The origin section is built on the
 * CI test that fails when a marketing number is hand-edited, which is
 * checkable, rather than a founding scene, which is not.
 */

/* ── Content ──────────────────────────────────────────────────────── */

/** Readable names for the generated sycophancy flags (docs/plans/sycophancy-mitigation.md). */
const CONTROL_NAMES: Record<keyof typeof SYCOPHANCY_CONTROLS, string> = {
  noApprovalGradient: 'No approval gradient to climb',
  mandatoryDissent: 'A dissenting generator in every run',
  confidencePenalty: 'A penalty for unsupported confidence',
  noStyleSelector: 'No warmth or personality setting',
  directPathEpistemicRules: 'Epistemic rules on direct answers',
  premiseAudit: 'An audit of the premises you state',
  revisionLicence: 'Licence to revise its own earlier answer',
  deaffirmEgress: 'A de-affirmation pass on answers',
  advisoryRoute: 'A route for personal advice',
  verificationStep: 'A verification step in action plans',
};
const CONTROLS = (Object.keys(CONTROL_NAMES) as Array<keyof typeof SYCOPHANCY_CONTROLS>).map((key) => ({
  key,
  name: CONTROL_NAMES[key],
  built: SYCOPHANCY_CONTROLS[key],
}));
const BUILT = CONTROLS.filter((c) => c.built).length;
const UNBUILT = CONTROLS.length - BUILT;

/** The page's own claims, labelled the way the pipeline labels an answer. */
const PAGE_CLAIMS: Array<{ claim: string; label: EpistemicLabelName }> = [
  { claim: 'A claim only its own model backs is downgraded, in code', label: 'VERIFIED' },
  { claim: 'Scoring and synthesis never share a bloc; a breach fails the build', label: 'VERIFIED' },
  { claim: 'The parallel generators never read each other', label: 'VERIFIED' },
  { claim: 'Every capability count here regenerates from the live registry', label: 'VERIFIED' },
  { claim: `${BUILT} of ${CONTROLS.length} sycophancy controls are in the code`, label: 'VERIFIED' },
  // Drops out once every control ships, rather than claiming "the other 0".
  ...(UNBUILT ? [{ claim: `The other ${UNBUILT} will help as much as the research says`, label: 'HYPOTHESIS' as const }] : []),
];

/** The three rules the mechanism section stands on. Each is checkable in the repository. */
const RULES = [
  {
    title: 'No model vouches for itself',
    text: 'A claim whose only backing is the model that produced it is downgraded from verified to hypothesis in code, before it reaches you. Verified is reserved for what a source outside the model can carry: a search result, a document you supplied, a check that executed.',
  },
  {
    title: 'No shared bloc',
    text: 'The model writing your final answer and the model pruning it never come from the same geopolitical bloc, and the generators span at least two. A routing configuration that violates it fails the build (after Buyl et al., npj AI, 2026).',
  },
  {
    title: 'Nothing travels between stages',
    text: 'The parallel generators never read one another, and nothing an earlier stage produced can enter a later stage as an instruction (after Papadopoulos et al., Mind Viruses, 2026).',
  },
];

/**
 * Each commitment names what it costs. A value that costs nothing to hold is
 * a slogan; the cost line is what makes the claim falsifiable.
 */
const COMMITMENTS = [
  {
    term: 'No model grades its own homework',
    detail: 'Self-reported confidence never becomes a verified label. Fewer confident-looking answers, more honest ones.',
    cost: 'Costs: the demo looks less impressive',
  },
  {
    term: 'Cross-bloc routing is enforced, not encouraged',
    detail: 'A preset that routes scoring and synthesis into the same bloc fails CI. It cannot be shipped around on a deadline.',
    cost: 'Costs: slower routing work, narrower model choice',
  },
  {
    term: 'Your conversations are not our training data',
    detail:
      'We do not train models on your questions or answers. Each model provider that handles a request has its own terms, listed on the privacy page.',
    cost: 'Costs: the asset every competitor is accumulating',
  },
  {
    term: 'You can read the code, and leave with it',
    detail:
      'Source-available under a Business Source Licence that converts to Apache-2.0 in 2030. Self-hostable today against your own Postgres and your own keys.',
    cost: 'Costs: lock-in, which was never ours to take',
  },
];

const FIGURES = [
  { value: CAPABILITIES.methods, label: 'Reasoning methods' },
  { value: CAPABILITIES.presets, label: 'Routing presets' },
  { value: CAPABILITIES.routableModels, label: 'Routable models' },
  { value: CAPABILITIES.testFiles, label: 'Test files' },
];


/* ── Page ─────────────────────────────────────────────────────────── */

export default function AboutPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: the thesis (left), this page's claims labelled (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Nothing asks</span>
              </span>
              <span className="site-line">
                <span>to be believed.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                A language model sounds the same whether it checked something or invented it. Reasoner
                exists to pull those two apart again, and to show you the seam.
              </p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>
                This page holds itself to the same rule: every claim on it is labelled with what it is.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/chat" className="site-button">
                  Start reasoning
                </Link>
                <Link href="/how-it-works" className={`site-link ${BODY}`}>
                  Read a complete run
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>This page, labelled</figcaption>
              <ul className="list-none">
                {PAGE_CLAIMS.map(({ claim, label }) => (
                  <li key={claim} className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-[var(--space-3)] ${ROW}`}>
                    <span>{claim}</span>
                    <span className={epistemicClassName(EPISTEMIC_TAG[label])}>{label}</span>
                  </li>
                ))}
              </ul>
            </figure>
          </div>
        </header>

        {/* ── The problem ── */}
        <Section id="problem" lines={['It stopped being', 'possible to unsee.']}>
          <Body>
            Ask a model something hard and it answers in the same calm register every time. The
            paragraph that took real evidence and the paragraph that took none are typographically
            identical. There is no tell. That is not a bug in any one model: it is what the training
            objective rewards.
          </Body>
          <Body>
            Then it gets worse. Ask the model whether it is confident and you have asked the system that
            produced the claim to grade the claim. Ask a second model from the same lab, in the same
            country, trained on much the same internet, and you have not bought a second opinion. You
            have bought an echo, and paid twice for it.
          </Body>
          <Body>
            Everyone in this market answered that by printing a confidence score. The thing worth having
            is underneath it: <strong className="font-semibold">who checked, against what, and what happens when they disagree.</strong>
          </Body>
        </Section>

        {/* ── Origin: a test file, not an anecdote ── */}
        <Section
          id="origin"
          lines={['We did not trust', 'ourselves either.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Regenerated on every commit</figcaption>
              <dl className="grid grid-cols-2">
                {FIGURES.map(({ value, label }) => (
                  <div key={label} className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-4)] odd:border-r">
                    <dt className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)] nums-tabular">
                      {value.toLocaleString('en-US')}
                    </dt>
                    <dd className="text-[var(--site-muted)]">{label}</dd>
                  </div>
                ))}
              </dl>
              <p className="px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
                Edit one by hand to make it sound better and a test fails.
              </p>
            </figure>
          }
        >
          <Body>
            The honest version of this section is not a founding anecdote. It is a test file. Every
            capability number on this site is regenerated from the live registry on every commit; edit
            one by hand and the build stops.
          </Body>
          <Body>
            That test was written early, deliberately, and pointed back at us: the same pressure that
            makes a model overstate its confidence operates on the people writing its marketing page. We
            did not think we were immune. We thought we should be checkable.
          </Body>
        </Section>

        {/* ── Mechanism ── */}
        <Section
          id="mechanism"
          lines={['Disagreement is', 'the product.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Three rules, each checkable</figcaption>
              <ul className="list-none">
                {RULES.map(({ title, text }) => (
                  <li key={title} className={ROW}>
                    <p className="flex flex-wrap items-center justify-between gap-[var(--space-3)]">
                      <span className="font-semibold">{title}</span>
                      <span className={epistemicClassName(EPISTEMIC_TAG.VERIFIED)}>VERIFIED</span>
                    </p>
                    <p className="mt-[var(--space-1)] text-[var(--site-muted)]">{text}</p>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            Most systems treat models arguing as noise to resolve before it reaches you. Here it is the
            signal. If four models from four labs converge, the convergence means something. If they
            split, you deserve to see where the fault line runs.
          </Body>
          <Body>
            {CAPABILITIES.methods} methods, not {CAPABILITIES.methods} prompts. Tree-of-Thoughts
            backtracks. Program-of-Thoughts executes the code it writes, in a sandbox with a wall-clock
            limit and a memory cap, so a reasoning step that claims a result has run it.
          </Body>
          <More href="/how-it-works">Read a complete production run</More>
        </Section>

        {/* ── Commitments ── */}
        <Section
          id="commitments"
          lines={['Every one of these', 'costs something.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Four commitments, and their price</figcaption>
              <dl>
                {COMMITMENTS.map(({ term, detail, cost }) => (
                  <div key={term} className={ROW}>
                    <dt className="font-semibold">{term}</dt>
                    <dd className="mt-[var(--space-1)] text-[var(--site-muted)]">{detail}</dd>
                    <dd className="mt-[var(--space-1)] text-[var(--site-accent)]">{cost}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            A value you can hold for free is not a value, it is a slogan. These four are in the build,
            in the licence, or in the bank, which is the only reason they are worth reading.
          </Body>
          <More href="/privacy">What is stored, and who handles it</More>
        </Section>

        {/* ── Unfinished: listed from the same generated flags the build
            checks, so this section cannot claim more than the code does. ── */}
        <Section
          id="unfinished"
          lines={['The part that', 'is not finished.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Sycophancy controls, detected at each commit</figcaption>
              <ul className="list-none">
                {CONTROLS.map(({ key, name, built }) => (
                  <li key={key} className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-[var(--space-3)] ${ROW}`}>
                    <span className={built ? '' : 'text-[var(--site-muted)]'}>{name}</span>
                    {/* A build status, not an epistemic claim: plain ink and muted
                        rather than the VERIFIED / HYPOTHESIS label colours. */}
                    <span className={`font-semibold ${built ? 'text-[var(--site-ink)]' : 'text-[var(--site-muted)]'}`}>
                      {built ? 'In code' : 'Not built'}
                    </span>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            Ibrahim et al. (2026) measured sycophancy across 3,075 participants: models affirm your own
            reasoning back at you, which buys comfort and does nothing measurable for answer quality.
          </Body>
          <Body>
            {BUILT} of the {CONTROLS.length} mitigations researched here are in the code, each found by a
            detector at every commit rather than ticked off by hand.{' '}
            {UNBUILT
              ? `The other ${UNBUILT} are designed and not built. When they land, this list changes by itself, and you can check it.`
              : 'Every one of them has landed, and the list beside this says so by itself.'}
          </Body>
          <More href="/capabilities#sycophancy">How the shipped controls work</More>
        </Section>

        {/* ── How the work is done ── */}
        <Section id="who" lines={['We read the paper', 'before the code.']} field>
          <Body>
            Before the mind-virus defences existed in code, they existed as a research note: the
            paper&rsquo;s findings in a table, each mitigation ranked by the effect size its authors
            measured, and an honest line at the top saying nothing had been implemented yet. Same for
            sycophancy. The note comes first. The code comes after, or it does not come at all.
          </Body>
          <Body>
            Those notes are in the repository, dated, with the commit they were checked against. It is
            not a work style anyone would choose for speed. It is the only one that produces a system you
            can argue with, and when something here turns out to be wrong we would rather hear it than not.
          </Body>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Ask what you</span>
            <span className="block">would check by hand.</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            Not a trivia question: the kind where being confidently wrong would cost you. That is the case
            this was built for, and the only fair test of whether any of the above is true.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/chat" className="site-button">
              Start reasoning
            </Link>
            <span className={BODY}>{FREE_CREDITS.toLocaleString('en-US')} credits a month on the free plan.</span>
          </div>
          <p className={`mt-[var(--space-12)] max-w-[60ch] ${BODY}`}>
            {SITE.name} is built and operated by {SITE.legalName}. Something here wrong, or a claim you
            want the receipts for?{' '}
            <Link href="/contact" className="site-link">
              Get in touch
            </Link>
            .
          </p>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
