import Link from 'next/link';
import type { ReactNode } from 'react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, PROVIDERS } from '@/lib/capabilities.generated';
import { SHOWCASE_IMAGES, SHOWCASE_PROMPT } from '@/lib/image-showcase';

/**
 * The home page argues one thing eight ways.
 *
 * Every capability below is the same mechanism seen from a different angle:
 * Reasoner runs work past models that disagree, then makes the disagreement
 * part of the output. Stating that once and then instancing it is what keeps
 * the page from reading as a feature grab-bag.
 *
 * Ordering is by strength of evidence, not by glamour. §1 leads because it is
 * the only claim here that is a deterministic guarantee rather than a
 * tendency — a rule in code, with no model in the loop. The proof for all of
 * it is one click away at /how-it-works, which is a captured production run.
 *
 * Copy discipline: every figure comes from `capabilities.generated.ts`, which
 * is regenerated from the live registry on each commit. Nothing here is typed
 * by hand, and nothing claims enforcement the code does not perform — see
 * docs/plans/landing-capability-pivot.md §3 for the claim-to-code table.
 */

/* ── Section chrome ───────────────────────────────────────────────── */

/**
 * Shares the run record's marginal-label idiom so the two pages read as one
 * document. Sections are separated by the §n marker and --section-y
 * whitespace alone — no rule between them. A line reads as a wall between
 * unrelated blocks; this page is one argument in eight parts, and the
 * marker's number is what says "new part," not a border.
 */
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

/** A cross-reference into the record or the docs. Never a second primary CTA. */
function Aside({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="link-smooth mt-[var(--space-6)] inline-flex font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--accent)] hover:text-[var(--accent-hover)]"
    >
      {children}
    </Link>
  );
}

/* ── Content ──────────────────────────────────────────────────────── */

/**
 * The four search actions the research loop can choose between at each
 * iteration (phases/_prism.py). "done" is omitted — it is a terminator, not
 * a capability.
 */
const RESEARCH_ACTIONS = [
  { name: 'General web', desc: 'Broad search across the open web.' },
  { name: 'Academic', desc: 'Papers and primary literature.' },
  { name: 'Discussion', desc: 'Forums and social platforms, where practice outruns publication.' },
  { name: 'Direct read', desc: 'Fetches and reads specific pages in full.' },
  { name: 'Your documents', desc: 'Searches files you upload alongside the question.' },
];

/** The real broad-then-narrow progression from the balanced-tier prompt. */
const QUERY_PROGRESSION = [
  'Tesla Model Y',
  'Tesla Model Y Q2 2025 earnings',
  'Tesla Model Y 2025 production cost breakdown',
];

/**
 * Methods with a distinct pipeline behind them, not a different prompt on a
 * shared one. Each maps to a module in src/reasoner/phases/.
 */
const METHODS = [
  { name: 'Tree-of-Thoughts', desc: 'Searches a branching space and backtracks out of dead ends.' },
  { name: 'Program-of-Thoughts', desc: 'Writes code and executes it in a sandbox as the reasoning step.' },
  { name: 'Chain-of-Verification', desc: 'Drafts, generates its own checks, then revises against them.' },
  { name: 'Debate', desc: 'Adversarial opening, rebuttal, and an independent judge.' },
  { name: 'Jury', desc: 'A panel of generator, critic, and verifier roles.' },
  { name: 'Scientific', desc: 'States hypotheses, then tries to falsify them.' },
  { name: 'Socratic', desc: 'Questions the premise until the hidden assumption surfaces.' },
  { name: 'Pre-Mortem', desc: 'Assumes the plan already failed and works backwards.' },
  { name: 'Bayesian', desc: 'Prior, likelihood, posterior — belief updated explicitly.' },
  { name: 'Dialectical', desc: 'Thesis against antithesis, resolved into synthesis.' },
  { name: 'Analogical', desc: 'Maps structure from a domain that already solved it.' },
  { name: 'Delphi', desc: 'Structured expert consensus across rounds.' },
  { name: 'Skeleton-of-Thought', desc: 'Outlines first, solves the branches in parallel, assembles.' },
  { name: 'Self-Discover', desc: 'Composes its own reasoning modules for the problem at hand.' },
];

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

/**
 * The masthead visual is the product's own output rather than a picture of
 * it. Every competing hero in this market opens on a gradient, an angled
 * dashboard, or an abstraction of neural connections; a visitor learns
 * nothing from any of them. Three claims — one per epistemic label — teach
 * the whole product in a glance, and the UNKNOWN row does the most work,
 * because a product admitting what it does not know on its own front door
 * is the argument the rest of the page spends eight sections making.
 *
 * Illustrative, and captioned as such under the card. The real captured run
 * is one click away at /how-it-works; dressing an example up as a record
 * would contradict §1 in the same viewport that states it.
 */
const SPECIMEN_CLAIMS = [
  {
    label: 'Verified',
    tone: 'epistemic-verified',
    claim: 'Aurora replicates storage six ways across three availability zones.',
    basis: 'source: AWS Aurora storage docs — read, not recalled',
  },
  {
    label: 'Hypothesis',
    tone: 'epistemic-hypothesis',
    claim: 'Your p99 write latency improves once the WAL leaves the instance.',
    basis: 'asserted by 3 of 4 models · no source · downgraded in code',
  },
  {
    label: 'Unknown',
    tone: 'epistemic-unknown',
    claim: 'What this costs you. I/O-optimized flips the pricing model entirely.',
    basis: 'needs your read/write ratio — not in the question',
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
            Every section below is an instance of the same claim, which is
            what stops the page reading as a list. */}
        <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-32)]">
          <div className="grid gap-[var(--space-12)] lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-start lg:gap-[var(--space-16)]">
            <div>
              {/* The mechanism, direct. No eyebrow needed — the claim reads
                  on its own and the product's own output (right column)
                  teaches what it means. */}
              <h1 className="max-w-[18ch] text-balance font-serif text-[144px] font-normal leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Models that disagree, on the record.
              </h1>

              {/* One sentence, in the order a sceptic needs it: rival labs
                  (why the disagreement is real) → kept, not averaged (what
                  is different) → by rule (why it can be trusted). The last
                  clause is the only emphasis above the fold and the only
                  claim a competitor cannot also make; it is a weight shift
                  rather than a colour so it never competes with the CTA.
                  The second paragraph that used to sit here is §1's job. */}
              <p className="prose-measure mt-[var(--space-8)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                Reasoner puts your question to models from rival labs, keeps their disagreement
                instead of averaging it away, and labels every claim{' '}
                <strong className="font-medium text-[var(--text)]">
                  verified, hypothesis, or unknown &mdash; by rule, not by asking a model how sure
                  it feels
                </strong>
                .
              </p>

              <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-3)] gap-x-[var(--space-8)]">
                <Link
                  href="/chat"
                  className="btn-lift group flex min-h-[var(--space-12)] items-center gap-[var(--space-2)] rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-base)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
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
                  className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[length:var(--text-base)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
                >
                  Read a complete run
                </Link>
              </div>

              {/* The number does what the word "free" cannot: it answers the
                  price objection and the what-is-the-catch objection in the
                  same six words. The one figure on this page that is not
                  machine-generated — keep it in step with /pricing. */}
              <p className="mt-[var(--space-4)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
                20 questions a month on the free tier.
              </p>
            </div>

            <div>
              <p className="prose-measure mt-[var(--space-8)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                One model checking its own work is one opinion. Reasoner runs every question past
                models from competing labs and rival geopolitical blocs, then keeps the
                disagreement in the output instead of averaging it away.
              </p>
            </div>
          </div>
        </header>

        {/* ── §1 Hallucination ──────────────────────────────────
            Leads the page because it is the only deterministic
            guarantee on it. */}
        <Section id="hallucination" marker="§1" name="Hallucination">
          <Heading>A model cannot vouch for itself.</Heading>
          <Lede>
            Most products ask a model whether it is confident and print the answer. Reasoner does
            not accept it. If a claim&rsquo;s only backing is the model that produced it, the label
            is downgraded from VERIFIED to HYPOTHESIS in code, before it reaches you.
          </Lede>
          <Body>
            VERIFIED is reserved for claims a non-model source can carry — a search result, a
            document you supplied, an executed check. This is a rule, not a prompt: no model is
            consulted when it runs, so no model can talk its way around it.
          </Body>

          <dl className="mt-[var(--space-10)] grid gap-[var(--space-6)] sm:grid-cols-2">
            <div className="border-t border-[var(--border)] pt-[var(--space-4)]">
              <dt className="epistemic-hypothesis pl-[var(--space-3)] font-sans text-[length:var(--text-sm)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
                Hypothesis
              </dt>
              <dd className="mt-[var(--space-3)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                The model asserted it and nothing else backs it. Plausible, reasoned, unconfirmed —
                and never dressed up as more.
              </dd>
            </div>
            <div className="border-t border-[var(--border)] pt-[var(--space-4)]">
              <dt className="epistemic-verified pl-[var(--space-3)] font-sans text-[length:var(--text-sm)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
                Verified
              </dt>
              <dd className="mt-[var(--space-3)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                A source outside the model carries it. Cited, and traceable back to the thing that
                carried it.
              </dd>
            </div>
          </dl>

          <Aside href="/how-it-works#synthesis">See the labels on a real synthesis →</Aside>
        </Section>

        {/* ── §2 Bias ───────────────────────────────────────────── */}
        <Section id="bias" marker="§2" name="Bias">
          <Heading>Scored by a model from a different bloc.</Heading>
          <Lede>
            Cross-lab is not enough. Two labs in the same country share an ideological prior, so
            routing a question past both proves less than it appears to. Reasoner routes so the
            model writing the final answer and the model pruning it never come from the same
            geopolitical bloc, and so the generators span at least two.
          </Lede>
          <Body>
            The constraint is grounded in published work — Buyl et al., <em>npj AI</em>{' '}
            2026, which
            finds the creator&rsquo;s bloc to be the dominant axis of a model&rsquo;s ideological
            bias. It is held by a validator and a test rather than by good intentions, so a preset
            that violates it fails the build.
          </Body>
          <Body>
            Separately, a dedicated critic tags each candidate answer with typed bias flags and
            subtracts a severity-weighted penalty from its score. Flagged candidates lose on the
            arithmetic, and you can see which flags they drew.
          </Body>

          <Aside href="/how-it-works#adjudication">See the score matrix and its bias flags →</Aside>
        </Section>

        {/* ── §3 Propagation ────────────────────────────────────── */}
        <Section id="propagation" marker="§3" name="Propagation">
          <Heading>An idea does not get to spread itself here.</Heading>
          <Lede>
            Systems that pass work between models have a failure mode a single model does not.
            Text that persuades one stage to carry it into the next can ride the whole pipeline
            and settle into what the system remembers. Reasoner is built so it has nowhere to
            travel.
          </Lede>
          <Body>
            Every stage that reads outside text — a web page, an earlier model, a recalled memory,
            an API caller — is told in its system prompt that such text is data and never
            instruction, and that anything asking to be repeated, preserved, or passed onward is a
            finding to report rather than an order to obey. The four generators never read each
            other, so nothing moves sideways between them. Recalled memory enters as a user
            message, never as an instruction, carrying the run and model it came from.
          </Body>
          <Body>
            The design follows Papadopoulos et al., <em>Mind Viruses: Self-Propagating Ideas in
            Multi-Agent LLM Systems</em> (2026), which measures each of these controls
            independently. The system-prompt warning is the one that held against fifteen
            generations of adversarial payloads; keeping memory out of the instruction channel is
            the difference the paper measures between most propagation succeeding and almost none
            of it. Both are held by tests, so a change that reopens either fails the build.
          </Body>

          <Aside href="/how-it-works#synthesis">See what a recalled memory looks like in a run →</Aside>
        </Section>

        {/* ── §4 Research ───────────────────────────────────────── */}
        <Section id="research" marker="§4" name="Research">
          <Heading>It searches like a researcher, not a search box.</Heading>
          <Lede>
            A single query returns what the query deserved. Reasoner runs an agentic loop that
            picks its own next move each iteration, goes broad before it goes narrow, and decides
            for itself when it has enough.
          </Lede>

          <ol
            role="list"
            className="mt-[var(--space-8)] grid list-none gap-[var(--space-4)] font-mono text-[length:var(--text-xs)] leading-[var(--lh-body)]"
          >
            {QUERY_PROGRESSION.map((query, i) => (
              <li key={query} className="flex gap-[var(--space-4)]">
                <span aria-hidden="true" className="nums-tabular shrink-0 text-[var(--text-subtle)]">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="text-[var(--text-2)]">{query}</span>
              </li>
            ))}
          </ol>

          <Body>
            At each step it chooses among five kinds of retrieval, then reads what it finds rather
            than skimming a snippet. At the deepest tier it plans five or more iterations and
            cross-references before it will stop.
          </Body>

          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-4)] sm:grid-cols-2">
            {RESEARCH_ACTIONS.map(({ name, desc }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Aside href="/how-it-works#evidence">See what one run actually read →</Aside>
        </Section>

        {/* ── §5 Methods ────────────────────────────────────────── */}
        <Section id="methods" marker="§5" name="Methods">
          <Heading>{CAPABILITIES.methods} methods. Not {CAPABILITIES.methods} prompts.</Heading>
          <Lede>
            Named reasoning techniques are usually sold as instructions bolted onto one chat
            completion. Here each is a separate pipeline with its own phases, its own model
            routing, and its own failure modes. Tree-of-Thoughts genuinely backtracks.
            Program-of-Thoughts genuinely executes the code it writes.
          </Lede>

          <dl className="mt-[var(--space-10)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-2">
            {METHODS.map(({ name, desc }) => (
              <div key={name}>
                <dt className="font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Each ships in a budget and a premium tier — {CAPABILITIES.presets} routing
            configurations in total, spanning {CAPABILITIES.routableModels.toLocaleString('en-US')}{' '}
            routable models. You can pick one, or let the router pick from the question.
          </Body>

          <Aside href="/docs">Read the method reference →</Aside>
        </Section>

        {/* ── §6 Images ─────────────────────────────────────────── */}
        <Section id="images" marker="§6" name="Images">
          <Heading>One prompt. Four images. Four labs.</Heading>
          <Lede>
            The same argument, applied to pixels. Four models from four different labs generate in
            parallel, so no single house style, outage, or content refusal decides what you get
            back. Every primary has a fallback behind it.
          </Lede>

          {/* One real run, left as it happened — including the two fallbacks. */}
          <figure className="mt-[var(--space-10)]">
            <p className="font-mono text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-muted)]">
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
                  <p className="mt-[var(--space-3)] font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                    {lab}
                    {fallback ? (
                      <sup className="font-normal text-[var(--warn)]" aria-hidden="true">
                        {' '}
                        †
                      </sup>
                    ) : null}
                  </p>
                  <p className="mt-[var(--space-1)] font-mono text-[length:var(--text-2xs)] leading-[var(--lh-body)] text-[var(--text-subtle)]">
                    {model} · {origin}
                  </p>
                </li>
              ))}
            </ul>

            <figcaption className="mt-[var(--space-6)] font-sans text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-muted)]">
              <span aria-hidden="true">†</span> Two of the configured primaries failed on this run
              and fallbacks took over mid-flight. Left as it happened — a chain you can watch
              working is worth more than one you have to take on faith.
            </figcaption>
          </figure>

          <Body>
            Model choice is automatic, made from the intent of your prompt and measured price
            rather than reputation. Ask for a vector and you get real SVG from a vector model —
            never a raster substitute dressed up as one. Reference images, five aspect ratios, and
            automatic prompt enhancement come as standard.
          </Body>
        </Section>

        {/* ── §7 Writing ────────────────────────────────────────── */}
        <Section id="writing" marker="§7" name="Writing">
          <Heading>Drafted, fact-checked, audited, then edited again.</Heading>
          <Lede>
            An article is not one generation. It moves through nine phases, and the fact-check is a
            hard gate — a run that fails it stops rather than quietly publishing around it. If the
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
                  className="nums-tabular shrink-0 font-mono text-[length:var(--text-xs)] text-[var(--text-subtle)]"
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)]">
                  {phase}
                </span>
              </li>
            ))}
          </ol>

          <Body>
            A style pass steers the prose away from the phrasing that marks machine writing — the
            stock openers, the reflexive tricolon, a long list of words that give it away. Sources
            are assembled from the links actually present in the finished text, so the bibliography
            describes the article rather than the intention.
          </Body>
        </Section>

        {/* ── §7 Ideas and code ─────────────────────────────────── */}
        <Section id="ideas" marker="§8" name="Ideas &amp; code">
          <Heading>Divergence where you want it. Rigour where you need it.</Heading>
          <Lede>
            Brainstorming generates widely, then deduplicates by meaning rather than wording,
            clusters what survives, and scores each idea on feasibility, novelty, and impact —
            with novelty weighted so the obvious answer cannot win by being obvious.
          </Lede>
          <Body>
            Coding runs the opposite way: specification, generation, review, tests, assembly. Code
            written under Program-of-Thoughts is executed in a sandbox with a wall-clock limit and
            a memory cap, so a reasoning step that claims a result has actually run it.
          </Body>
        </Section>

        {/* ── Terms ─────────────────────────────────────────────── */}
        <Section marker="—" name="Terms">
          <Heading>Where your data sits.</Heading>
          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-2">
            {TERMS.map(({ term, detail }) => (
              <div key={term}>
                <dt className="font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {term}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-[var(--space-8)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
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
                  className="btn-lift flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-base)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
                >
                  Ask a question
                </Link>
                <Link
                  href="/pricing"
                  className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[length:var(--text-base)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
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
