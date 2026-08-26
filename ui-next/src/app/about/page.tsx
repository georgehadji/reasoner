import Link from 'next/link';
import type { ReactNode } from 'react';

import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES } from '@/lib/capabilities.generated';
import { SITE } from '@/lib/site';

/**
 * The About page argues the same thing the home page argues, turned inward.
 *
 * The old version of this page was a four-item capability grid — the same
 * features as `/`, restated with less evidence. That is the one thing an
 * About page cannot be: a visitor who reaches it has already read the
 * feature copy and is here to decide whether the person behind it can be
 * trusted.
 *
 * So the page applies the product's own rule to itself. Claims a reader can
 * go and check are marked VERIFIED; the one thing that is researched but not
 * yet built is marked HYPOTHESIS and says so on the page meant to sell it.
 * Admitting unfinished work is load-bearing here, not a disclaimer — a
 * system whose premise is "you should not have to trust us" cannot ask for
 * trust in its own biography.
 *
 * Deliberately absent: an origin anecdote. §2 is built on the CI test that
 * fails when a marketing number is hand-edited, which is checkable, rather
 * than a founding scene, which is not. Same rule as everything else here.
 *
 * Shares the marginal-§n idiom and the Section/Heading/Lede/Body helpers
 * with LandingPage so the two read as one document. The helpers are copied
 * rather than imported: importing them would pull the whole landing module
 * into this route's bundle for four six-line functions.
 */

/* ── Type helpers (mirrors LandingPage) ───────────────────────────── */

function Section({
  id,
  marker,
  name,
  children,
}: {
  id?: string;
  marker: string;
  name: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="mx-auto w-full max-w-[var(--width-wide)] scroll-mt-[var(--space-20)] px-[var(--gutter)] py-[var(--section-y)]"
    >
      <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
        <div className="lg:sticky lg:top-[var(--space-24)] lg:self-start">
          <p className="nums-tabular font-mono text-[length:var(--text-xs)] text-[var(--accent)]">
            {marker}
          </p>
          <p className="mt-[var(--space-1)] font-sans text-[length:var(--text-xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
            {name}
          </p>
        </div>
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-serif text-[length:var(--text-3xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
      {children}
    </h2>
  );
}

function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-6)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
      {children}
    </p>
  );
}

function Body({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-4)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/**
 * A claim carrying its own epistemic label, using the same two utilities the
 * run record uses (globals.css). The label is not decoration: VERIFIED here
 * means a reader can open the repository and check it, which is the same bar
 * the pipeline applies to an answer.
 */
function Claim({ tone, children }: { tone: 'verified' | 'hypothesis'; children: ReactNode }) {
  return (
    <div
      className={`prose-measure mt-[var(--space-8)] pl-[var(--space-4)] ${
        tone === 'verified' ? 'epistemic-verified' : 'epistemic-hypothesis'
      }`}
    >
      <p className="font-sans text-[length:var(--text-xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
        {tone === 'verified' ? 'Verified' : 'Hypothesis'}
      </p>
      <p className="mt-[var(--space-2)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
        {children}
      </p>
    </div>
  );
}

/* ── Content ──────────────────────────────────────────────────────── */

/**
 * Each commitment names what it costs. A value that costs nothing to hold is
 * a slogan; the cost line is what makes the claim falsifiable, and it is the
 * only reason this section earns its place over a generic values list.
 */
const COMMITMENTS = [
  {
    term: 'No model grades its own homework',
    detail:
      'Self-reported confidence never becomes a VERIFIED label. Fewer confident-looking answers, more honest ones.',
    cost: 'Costs: the demo looks less impressive',
  },
  {
    term: 'Cross-bloc routing is enforced, not encouraged',
    detail:
      'A preset that routes scoring and synthesis into the same bloc fails CI. It cannot be shipped around on a deadline, and that is the point.',
    cost: 'Costs: slower routing work, narrower model choice',
  },
  {
    term: 'Your conversations are not training data',
    detail:
      'Encrypted in transit and at rest, private by default. There is no version of this where your questions become somebody’s next corpus.',
    cost: 'Costs: the asset every competitor is accumulating',
  },
  {
    term: 'You can read the code, and leave with it',
    detail:
      'Source-available under a Business Source Licence that converts to Apache-2.0 in 2030. Self-hostable today against your own Postgres, your keys, your infrastructure.',
    cost: 'Costs: lock-in, which was never ours to take',
  },
] as const;

const FIGURES = [
  { value: CAPABILITIES.methods, label: 'Reasoning methods' },
  { value: CAPABILITIES.presets, label: 'Routing presets' },
  { value: CAPABILITIES.routableModels, label: 'Routable models' },
  { value: CAPABILITIES.testFiles, label: 'Test files' },
] as const;

/* ── Page ─────────────────────────────────────────────────────────── */

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead ───────────────────────────────────────────
            The headline is the page's thesis and its method at once:
            it tells the reader not to take the page on faith, which is the
            only opening consistent with the product. */}
        <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-32)]">
          <div className="grid gap-[var(--space-12)] lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-start lg:gap-[var(--space-16)]">
            <div>
              <h1 className="max-w-[16ch] text-balance font-serif text-[length:var(--text-6xl)] font-normal leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Nothing here asks to be believed.
              </h1>

              <p className="prose-measure mt-[var(--space-8)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                Reasoner exists because of one uncomfortable fact: a language model sounds exactly
                the same whether it checked something or invented it. Fluency came free.{' '}
                <strong className="font-medium text-[var(--text)]">Truth did not.</strong> Everything
                built here since is an attempt to pull those two apart again, and to hand you the
                seam so you can look at it yourself.
              </p>
            </div>

            <div>
              <p className="prose-measure mt-[var(--space-8)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                This page is that same rule turned on itself. Every claim below is marked with what
                it actually is: something you can go and verify, or something still only hoped for.
              </p>
            </div>
          </div>
        </header>

        {/* ── §1 ─────────────────────────────────────────────── */}
        <Section id="problem" marker="§1" name="The problem">
          <Heading>It stopped being possible to unsee.</Heading>
          <Lede>
            Ask a model something hard and it answers in the same calm register every time. The
            paragraph that took real evidence and the paragraph that took none are typographically
            identical. There is no tell. That is not a bug in any one model &mdash; it is what the
            training objective rewards.
          </Lede>
          <Body>
            Then it gets worse. Ask the model whether it is confident and you have asked the system
            that produced the claim to grade the claim. Ask a second model from the same lab, in the
            same country, trained on much the same internet, and you have not bought a second
            opinion. You have bought an echo, and paid twice for it.
          </Body>
          <Body>
            Everyone in this market answered that by printing a confidence score. A score was never
            the thing worth having. The thing worth having is underneath it:{' '}
            <strong className="font-medium text-[var(--text)]">
              who checked, against what, and what happens when they disagree.
            </strong>
          </Body>
        </Section>

        {/* ── §2 ─────────────────────────────────────────────── */}
        <Section id="origin" marker="§2" name="Where it started">
          <Heading>We did not trust ourselves either.</Heading>
          <Lede>
            The honest version of this section is not a founding anecdote. It is a test file.
          </Lede>
          <Body>
            Every capability number on this site &mdash; {CAPABILITIES.methods} methods,{' '}
            {CAPABILITIES.presets} presets, {CAPABILITIES.routableModels.toLocaleString('en-US')}{' '}
            routable models &mdash; is regenerated from the live registry on every commit. Edit one
            by hand to make it sound better and a test fails, and the build stops. That test was
            written early, deliberately, and pointed back at us: the same pressure that makes a
            model overstate its confidence operates on the people writing its marketing page. We did
            not think we were immune. We thought we should be checkable.
          </Body>
          <Body>
            That instinct is the whole product in miniature. Not a wrapper, not a prompt library.
            A pipeline that takes a question apart, routes the pieces to models built by rivals,
            keeps their disagreement instead of averaging it flat, and refuses to stamp anything
            verified on a model&rsquo;s say-so &mdash; because a claim that cannot be checked should
            not be dressed as one that can.
          </Body>
        </Section>

        {/* ── §3 ─────────────────────────────────────────────── */}
        <Section id="mechanism" marker="§3" name="What it does">
          <Heading>Disagreement is the product, not a defect to smooth over.</Heading>
          <Lede>
            Most systems treat models arguing as noise to resolve before it reaches you. Here it is
            the signal. If four models from four labs converge, the convergence means something. If
            they split, you deserve to see where the fault line runs &mdash; that is precisely the
            question worth your own judgment.
          </Lede>

          <Claim tone="verified">
            A claim whose only backing is the model that produced it is downgraded from VERIFIED to
            HYPOTHESIS <strong className="font-medium text-[var(--text)]">in code</strong>, before it
            reaches you. No model is consulted when that rule runs, so no model can talk its way
            around it. VERIFIED is reserved for what a source outside the model can carry: a search
            result, a document you supplied, a check that actually executed.
          </Claim>

          <Claim tone="verified">
            The model writing your final answer and the model pruning it never come from the same
            geopolitical bloc, and the generators span at least two. Two labs in one country share
            an ideological prior; the constraint follows Buyl et al., <em>npj AI</em> (2026), which
            finds a creator&rsquo;s bloc to be the dominant axis of a model&rsquo;s bias. It is held
            by a validator and a test rather than by good intentions, so a routing configuration
            that violates it fails the build.
          </Claim>

          <Claim tone="verified">
            The parallel generators never read one another, and nothing an earlier stage produced
            can enter a later stage as an instruction. This follows Papadopoulos et al.,{' '}
            <em>Mind Viruses: Self-Propagating Ideas in Multi-Agent LLM Systems</em> (2026): in any
            system that passes work between models, text that persuades one stage to carry it
            onward can ride the entire pipeline and settle into what the system remembers. Here it
            has nowhere to travel.
          </Claim>

          <dl className="mt-[var(--space-12)] grid grid-cols-2 gap-[var(--space-6)] border-y border-[var(--border)] py-[var(--space-8)] sm:grid-cols-4">
            {FIGURES.map(({ value, label }) => (
              <div key={label}>
                <dt className="nums-tabular font-mono text-[length:var(--text-2xl)] font-medium leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                  {value.toLocaleString('en-US')}
                </dt>
                <dd className="mt-[var(--space-1)] font-sans text-[length:var(--text-xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
                  {label}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            {CAPABILITIES.methods} methods, not {CAPABILITIES.methods} prompts. Tree-of-Thoughts
            genuinely backtracks. Program-of-Thoughts genuinely executes the code it writes, in a
            sandbox with a wall-clock limit and a memory cap &mdash; so a reasoning step that claims
            a result has actually run it.
          </Body>

          <Link
            href="/how-it-works"
            className="link-smooth mt-[var(--space-6)] inline-flex font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--accent)] hover:text-[var(--accent-hover)]"
          >
            Read a complete production run &rarr;
          </Link>
        </Section>

        {/* ── §4 ─────────────────────────────────────────────── */}
        <Section id="commitments" marker="§4" name="Commitments">
          <Heading>Every one of these costs something.</Heading>
          <Lede>
            A value you can hold for free is not a value, it is a slogan. These four are in the
            build, in the licence, or in the bank, which is the only reason they are worth reading.
          </Lede>

          <dl className="mt-[var(--space-10)] grid gap-x-[var(--space-8)] gap-y-[var(--space-8)] sm:grid-cols-2">
            {COMMITMENTS.map(({ term, detail, cost }) => (
              <div key={term}>
                <dt className="font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {term}
                </dt>
                <dd className="mt-[var(--space-2)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {detail}
                </dd>
                <dd className="mt-[var(--space-2)] font-mono text-[length:var(--text-2xs)] leading-[var(--lh-body)] text-[var(--accent)]">
                  {cost}
                </dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* ── §5 ─────────────────────────────────────────────── */}
        <Section id="unfinished" marker="§5" name="What we owe you">
          <Heading>The part that is not finished.</Heading>

          <Claim tone="hypothesis">
            There is a second failure mode that has been researched here and{' '}
            <strong className="font-medium text-[var(--text)]">not yet shipped</strong>: sycophancy.
            Ibrahim et al. (2026) measured it across 3,075 participants and found that models
            actively affirm your own reasoning back at you &mdash; and that this buys emotional
            comfort while doing nothing measurable for answer quality. The analysis is written up,
            ranked by the effect sizes the study actually measured. The mitigations are not built.
            When they are, this section will say so, and you will be able to check.
          </Claim>

          <Body>
            That admission sits on the page meant to sell you the product because the alternative is
            asking you to trust a system whose entire premise is that you should not have to.
          </Body>
        </Section>

        {/* ── §6 ─────────────────────────────────────────────── */}
        <Section id="who" marker="§6" name="Who">
          <Heading>We read the paper before we write the code.</Heading>
          <Lede>
            Before the mind-virus defences existed in code, they existed as a research note: the
            paper&rsquo;s findings in a table, each mitigation ranked by the effect size its authors
            actually measured, and an honest line at the top saying nothing had been implemented
            yet. Same for sycophancy. The note comes first. The code comes after, or it does not
            come at all.
          </Lede>
          <Body>
            The mind-virus note is in the repository, dated, with the commit it was verified
            against. That is not a work style anyone would choose for speed. It is the only one
            that produces a system you can argue with, and it is why this took as long as it did.
          </Body>
          <Body>
            None of it is written to impress an investor. The same standard the pipeline applies to
            an answer is the one we try to hold ourselves to, and when something here turns out to
            be wrong we would rather hear it than not.
          </Body>
        </Section>

        {/* ── Close ──────────────────────────────────────────── */}
        <Section id="start" marker="§7" name="Start">
          <Heading>Ask it something you would check by hand.</Heading>
          <Lede>
            Not a trivia question &mdash; the kind where being confidently wrong would actually cost
            you. That is the case this was built for, and the only fair test of whether any of the
            above is true.
          </Lede>

          <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-3)] gap-x-[var(--space-8)]">
            <Link
              href="/chat"
              className="btn-lift group flex min-h-[var(--space-12)] items-center gap-[var(--space-2)] rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-base)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
            >
              Start reasoning
              <span
                aria-hidden="true"
                className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
              >
                &rarr;
              </span>
            </Link>
            <span className="font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
              20 questions a month on the free tier.
            </span>
          </div>

          <p className="prose-measure mt-[var(--space-12)] border-t border-[var(--border)] pt-[var(--space-6)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
            {SITE.name} is built and operated by {SITE.legalName}. Something here
            wrong, or a claim you want the receipts for?{' '}
            <Link
              href="/contact"
              className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              Get in touch
            </Link>
            .
          </p>
        </Section>
      </main>

      <SiteFooter />
    </div>
  );
}
