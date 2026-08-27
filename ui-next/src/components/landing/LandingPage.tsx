import Link from 'next/link';
import { DisagreementField } from '@/components/landing/DisagreementField';
import { MechanismDiagram } from '@/components/landing/MechanismDiagram';
import { Aside, Body, Heading, Lede, Section } from '@/components/landing/prose';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, PROVIDERS } from '@/lib/capabilities.generated';
import { SHOWCASE_IMAGES, SHOWCASE_PROMPT } from '@/lib/image-showcase';

/**
 * The home page states one claim and then shows the product's own output
 * making good on it.
 *
 * The mechanism argument used to run down this page as nine numbered
 * sections; it now lives at /capabilities, with its anchors and its numbering
 * intact. What stays here is the claim, the four-stage rail that frames it,
 * and the exhibits — a real image run and a real article run — because those
 * are the parts a first-time reader can check without being asked to read an
 * essay first.
 *
 * Copy discipline: every figure comes from `capabilities.generated.ts`, which
 * is regenerated from the live registry on each commit. Nothing here is typed
 * by hand, and nothing claims enforcement the code does not perform — see
 * docs/plans/landing-capability-pivot.md §3 for the claim-to-code table.
 */

/* ── Content ────────────────────────────────────────────── */

/** The nine article phases, in order (application/flows/article.py). */
const ARTICLE_PHASES = [
  'Evidence collection',
  'Argument map',
  'First draft',
  'Fact check',
  'Structural review',
  'Developmental edit',
  'Style and copy edit',
  'Final audit',
  'Synthesis',
];

const TERMS = [
  {
    term: 'Source-available',
    detail: 'Read the code under a Business Source License. It converts to Apache-2.0 in 2030.',
  },
  {
    term: 'Self-hostable',
    detail: 'A full Docker stack against your own Postgres and Valkey. Your keys, your infrastructure.',
  },
  {
    term: 'Encrypted at rest and in transit',
    detail: 'Session and memory data is encrypted on both legs.',
  },
  {
    term: 'Not training data',
    detail: 'We do not train on your conversations. They stay private by default.',
  },
];

/* ── Page ─────────────────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead ───────────────────────────────────────────
            States the spine once, then proves it in the same viewport. Left
            column is the argument, right column is the product's own output.
            Everything below is an instance of the same claim, which is what
            stops the page reading as a list.

            Holds the viewport so the rail starts at the fold rather than
            peeking above it. min-h rather than h: on a short window the content grows
            the box instead of being clipped inside it, and centring by flex
            cannot then push the top of the headline out of reach. svh rather
            than vh because mobile vh is measured against the LARGE viewport,
            so a 100vh hero sits taller than the screen until the browser
            chrome retracts. SiteHeader is fixed, so it costs no layout height
            here -- the top padding is what keeps the headline clear of it. */}
        <header className="relative mx-auto flex min-h-svh w-full max-w-[var(--width-wide)] flex-col justify-center px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-48)]">
          <DisagreementField />

          <div className="relative grid gap-[var(--space-12)] lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-start lg:gap-[var(--space-16)]">
            <div>
              {/* The mechanism, direct. No eyebrow needed — the claim reads
                  on its own and the product's own output (right column)
                  teaches what it means. */}
              <h1 className="max-w-[18ch] text-balance font-serif text-[34pt] font-normal leading-[var(--lh-display)] sm:text-[55pt] lg:text-[89pt] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Models that disagree, on the record.
              </h1>
            </div>

            {/* Drops to the foot of the row so the paragraph's last line sits
                on the headline's baseline. The two columns are one sentence
                and its proof, and hanging the short one from the top of a
                three-line display leaves it floating against nothing. */}
            <div className="lg:self-end">
              {/* One sentence, in the order a sceptic needs it: rival labs
                  (why the disagreement is real) → kept, not averaged (what
                  is different) → by rule (why it can be trusted). The last
                  clause is the only emphasis above the fold and the only
                  claim a competitor cannot also make; it is a weight shift
                  rather than a colour so it never competes with the CTA. */}
              <p className="prose-measure font-serif text-[21pt] leading-[1.6] text-[var(--text-2)]">
                Reasoner puts your question to models from rival labs and rival geopolitical blocs,
                keeps their disagreement instead of averaging it away, and labels every claim{' '}
                <strong className="font-medium text-[var(--text)]">
                  verified, hypothesis, or unknown. By rule, not by asking a model how sure it
                  feels.
                </strong>
              </p>
            </div>
          </div>

          {/* Sits under both columns so the claim and the mechanism have both
              landed before the reader is asked to act. */}
          <div className="relative mt-[var(--space-12)] flex flex-wrap items-center justify-center gap-[var(--space-3)] gap-x-[var(--space-8)]">
            <Link
              href="/chat"
              className="btn-lift group flex min-h-[var(--space-12)] items-center gap-[var(--space-2)] rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
            >
              Ask a question
              <span
                aria-hidden="true"
                className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
              >
                &rarr;
              </span>
            </Link>
            {/* Points at a captured production run, not a demo request.
                The reader this headline attracts is a sceptic, and a
                sceptic converts on evidence they can read alone. */}
            <Link
              href="/how-it-works"
              className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[13pt] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
            >
              Read a complete run
            </Link>
          </div>

          {/* The number does what the word "free" cannot: it answers the
              price objection and the what-is-the-catch objection in the
              same six words. The one figure on this page that is not
              machine-generated — keep it in step with /pricing. */}
          <p className="relative mt-[var(--space-4)] text-center font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            20 questions a month on the free tier.
          </p>
        </header>

        {/* ── Mechanism ─────────────────────────────────────────
            The page's correction to its own worst habit. Multi-perspective
            analysis is the default preset, and a default has a way of
            becoming the description — visitors, and the product's own
            copy, kept calling that one pipeline "Reasoner." The rail is
            what is actually true of every run; the method is stage 03's
            replaceable part.

            It sits directly under the masthead because these four stages
            are the frame everything else hangs on, and because the four
            failures it names are what the reader arrived carrying. Each
            stage links into its section on /capabilities, which is where
            the argument for it now lives. */}
        <Section tone="invert">
          <Heading>Four failures, stopped at four different points.</Heading>
          <Lede>
            Bias, mind-virus propagation, sycophancy, and hallucination are the four ways a
            confident answer goes wrong, and none of them is a knowledge problem, so a larger
            model fixes none of them. Reasoner meets each at a different stage of the run.
          </Lede>
          <Body>
            What sits inside the reasoning stage changes with the question: {CAPABILITIES.methods}{' '}
            methods, from adversarial debate to code that is actually executed. Multi-perspective
            analysis is one of them, and the default. It is not the product. The four defences
            hold whichever one runs.
          </Body>

          <MechanismDiagram />

          <Aside href="/capabilities">Read the argument for each &rarr;</Aside>
        </Section>

        {/* ── §1 Images ──────────────────────────────────────────── */}
        <Section id="images" marker="§1" name="Images">
          <Heading>One prompt. Four images. Four labs.</Heading>
          <Lede>
            The same argument, applied to pixels. Four models from four different labs generate in
            parallel, so no single house style, outage, or content refusal decides what you get
            back. Every primary has a fallback behind it.
          </Lede>

          {/* One real run, left as it happened — including the two fallbacks. */}
          <figure className="mt-[var(--space-10)]">
            <p className="font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              &ldquo;{SHOWCASE_PROMPT}&rdquo;
            </p>

            <ul
              role="list"
              className="mt-[var(--space-6)] grid list-none gap-[var(--space-4)] sm:grid-cols-2 lg:grid-cols-4"
            >
              {SHOWCASE_IMAGES.map(({ src, model, lab, origin, fallback }) => (
                <li key={src} className="card-hover">
                  <img
                    src={src}
                    alt={`${lab}'s interpretation of the prompt: a wooden reading chair beside a tall gallery window in morning light`}
                    width={720}
                    height={720}
                    loading="lazy"
                    decoding="async"
                    className="aspect-square w-full border border-[var(--border)] object-cover"
                  />
                  <p className="mt-[var(--space-3)] font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                    {lab}
                    {fallback ? (
                      <sup className="font-normal text-[var(--warn)]" aria-hidden="true">
                        {' '}
                        †
                      </sup>
                    ) : null}
                  </p>
                  <p className="mt-[var(--space-1)] font-mono text-[8pt] leading-[var(--lh-body)] text-[var(--text-subtle)]">
                    {model} · {origin}
                  </p>
                </li>
              ))}
            </ul>

            <figcaption className="mt-[var(--space-6)] font-sans text-[8pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              <span aria-hidden="true">†</span> Two of the configured primaries failed on this run
              and fallbacks took over mid-flight. Left as it happened. A chain you can watch
              working is worth more than one you have to take on faith.
            </figcaption>
          </figure>

          {/* Deliberately does NOT restate the routing. Which four models
              answered, why they came from four labs, and what happens when one
              refuses is /capabilities §4's argument; repeating it here would
              make the page claim the same mechanism twice and leave the
              exhibit doing the explaining. This paragraph carries only what
              that section does not: the controls a reader gets to hold. */}
          <Body>
            Reference images, five aspect ratios, and automatic prompt enhancement come as
            standard. Which four models answered this one, and what happens when one of them
            refuses, is the routing described under{' '}
            <Link
              href="/capabilities#image-making"
              className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              image making
            </Link>
            .
          </Body>

          <Aside href="/capabilities#image-making">See how these four were picked →</Aside>
        </Section>

        {/* ── §2 Writing ─────────────────────────────────────────── */}
        <Section id="writing" marker="§2" name="Writing">
          <Heading>Drafted, fact-checked, audited, then edited again.</Heading>
          <Lede>
            An article is not one generation. It moves through nine phases, and the fact-check is a
            hard gate: a run that fails it stops rather than quietly publishing around it. If the
            final audit fails, the piece goes back for another editorial pass automatically.
          </Lede>

          <ol
            role="list"
            className="mt-[var(--space-8)] grid list-none gap-[var(--space-3)] sm:grid-cols-3"
          >
            {ARTICLE_PHASES.map((phase, i) => (
              <li key={phase} className="flex gap-[var(--space-3)] border-t border-[var(--border)] pt-[var(--space-3)]">
                <span
                  aria-hidden="true"
                  className="nums-tabular shrink-0 font-mono text-[8pt] text-[var(--text-subtle)]"
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-2)]">
                  {phase}
                </span>
              </li>
            ))}
          </ol>

          <Body>
            Phase seven is the style pass described under{' '}
            <Link
              href="/capabilities#voice"
              className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              voice
            </Link>
            , run here against a finished draft rather than a first answer. Sources are assembled
            from the links actually present in that draft, so the bibliography describes the
            article rather than the intention.
          </Body>
        </Section>

        {/* ── §3 Code ───────────────────────────────────────────
            Brainstorming used to open this section, which left it
            trying to carry ideation and code in two sentences and
            serving neither. Ideation has its own section on
            /capabilities; this says the one thing about code worth
            the space. */}
        <Section id="code" marker="§3" name="Code">
          <Heading>Reasoning that runs, not reasoning that claims.</Heading>
          <Lede>
            Coding runs the opposite way from ideation: specification, generation, review, tests,
            assembly. There is a right answer, and nothing is served by diverging from it.
          </Lede>
          <Body>
            Code written under Program-of-Thoughts is executed in a sandbox with a wall-clock limit
            and a memory cap, so a reasoning step that claims a result has actually produced it.
          </Body>
        </Section>

        {/* ── Terms ─────────────────────────────────────────────── */}
        <Section name="Terms">
          <Heading>Where your data sits.</Heading>
          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-2">
            {TERMS.map(({ term, detail }) => (
              <div key={term}>
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {term}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-[var(--space-8)] font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            Routes across {PROVIDERS.join(', ')}, and{' '}
            {CAPABILITIES.routableModels.toLocaleString('en-US')} models through OpenRouter. Full
            detail in{' '}
            <Link href="/security" className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]">
              security
            </Link>
            ,{' '}
            <Link href="/privacy" className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]">
              privacy
            </Link>
            , and{' '}
            <Link
              href="/subprocessors"
              className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              sub-processors
            </Link>
            .
          </p>
        </Section>

        {/* ── Close ─────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] py-[var(--section-y)]">
          <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div aria-hidden="true" />
            <div className="min-w-0">
              <Heading>Ask it something you would check by hand.</Heading>
              <Lede>
                The kind of question where being confidently wrong would cost you. That is the case
                this was built for.
              </Lede>
              <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-4)]">
                <Link
                  href="/chat"
                  className="btn-lift flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
                >
                  Ask a question
                </Link>
                <Link
                  href="/pricing"
                  className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[13pt] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
                >
                  See pricing
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
