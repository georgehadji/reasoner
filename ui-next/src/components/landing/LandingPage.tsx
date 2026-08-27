import Link from 'next/link';
import type { ReactNode } from 'react';
import { DisagreementField } from '@/components/landing/DisagreementField';
import { MechanismDiagram } from '@/components/landing/MechanismDiagram';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, PROVIDERS, SYCOPHANCY_CONTROLS } from '@/lib/capabilities.generated';
import { SHOWCASE_IMAGES, SHOWCASE_PROMPT } from '@/lib/image-showcase';

/**
 * The home page argues one thing twelve ways.
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
 * unrelated blocks; this page is one argument in twelve parts, and the
 * marker's number is what says "new part," not a border.
 */
function Section({
  id,
  marker,
  name,
  tone,
  children,
}: {
  id?: string;
  /**
   * Omit both to drop the marginal column and run the content across the
   * full measure. The band does that: it is already set apart by its own
   * ground, so a marker labelling it is the second device doing the first
   * device's job, and the four stages would rather have the 9rem.
   */
  marker?: string;
  name?: string;
  /**
   * `invert` runs the section against the page's ground, dark on the ivory
   * theme and ivory on the dark one, and takes it full-bleed. A band that
   * stops at the 72rem measure reads as a card rather than as a change of
   * ground. The inversion is a token swap in globals.css; nothing inside a
   * section needs to know which ground it is standing on.
   */
  tone?: 'invert';
  children: ReactNode;
}) {
  const labelled = marker !== undefined || name !== undefined;

  const inner = (
    <section
      id={id}
      className="mx-auto w-full max-w-[var(--width-wide)] scroll-mt-[var(--space-20)] px-[var(--gutter)] py-[var(--section-y)]"
    >
      <div
        className={
          labelled
            ? 'grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]'
            : ''
        }
      >
        {labelled ? (
          /* Parks alongside the section it labels, so the marker stays
             visible for as long as the section it names is. */
          <div className="lg:sticky lg:top-[var(--space-24)] lg:self-start">
            {marker ? (
              <p className="nums-tabular font-mono text-[8pt] text-[var(--accent)]">{marker}</p>
            ) : null}
            <p className="mt-[var(--space-1)] font-sans text-[8pt] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
              {name}
            </p>
          </div>
        ) : null}
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );

  if (tone !== 'invert') return inner;

  return (
    <div className="scroll-grow invert-band bg-[var(--bg)] text-[var(--text)]">{inner}</div>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-serif text-[21pt] sm:text-[34pt] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
      {children}
    </h2>
  );
}

function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-6)] font-serif text-[21pt] leading-[var(--lh-body)] text-[var(--text-2)]">
      {children}
    </p>
  );
}

function Body({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure mt-[var(--space-4)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
      {children}
    </p>
  );
}

/** A cross-reference into the record or the docs. Never a second primary CTA. */
function Aside({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="link-smooth mt-[var(--space-6)] inline-flex font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--accent)] hover:text-[var(--accent-hover)]"
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
 * The creativity tier every generated idea carries out of the Verbalized
 * Sampling rounds (phases/brainstorming.py). The tag is the model's own, which
 * is the whole point of showing it: it declares where in its own distribution
 * the idea came from, so the safe ones cannot pass themselves off as reaches.
 */
const IDEA_TIERS = [
  {
    name: 'Conventional',
    desc: 'What the field would already say. Kept, because a baseline is worth seeing named.',
  },
  {
    name: 'Lateral',
    desc: 'A move sideways. Structure borrowed from a domain that is not this one.',
  },
  {
    name: 'Disruptive',
    desc: 'Low probability by the model’s own reckoning. Usually wrong, occasionally the answer.',
  },
];

/**
 * The capability families an image prompt is classified into
 * (hypergate/sub_agents/image_model_selector.py, mirrored in
 * infrastructure/llm/image_model_catalogue.py). The family decides the
 * candidate pool before any model runs. "General" is also where an
 * unrecognised or low-confidence call lands, which is why it is described as
 * a floor rather than as a category of its own.
 */
const IMAGE_FAMILIES = [
  { name: 'Vector', desc: 'Logos, icons, flat marks — routed to a model that emits real SVG.' },
  { name: 'Photoreal', desc: 'People, products, scenes. Anything that has to survive being looked at closely.' },
  { name: 'Text in image', desc: 'Posters, signage, labels — only the models that can actually spell.' },
  { name: 'Design', desc: 'Layouts and brand assets, where the composition is the constraint.' },
  { name: 'Reference edit', desc: 'Edits or restyles an image you supply, on models that accept one.' },
  { name: 'General', desc: 'Everything else, and where an unsure call lands rather than guessing.' },
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
  { name: 'Bayesian', desc: 'Prior, likelihood, posterior. Belief updated explicitly.' },
  { name: 'Dialectical', desc: 'Thesis against antithesis, resolved into synthesis.' },
  { name: 'Analogical', desc: 'Maps structure from a domain that already solved it.' },
  { name: 'Delphi', desc: 'Structured expert consensus across rounds.' },
  { name: 'Skeleton-of-Thought', desc: 'Outlines first, solves the branches in parallel, assembles.' },
  { name: 'Self-Discover', desc: 'Composes its own reasoning modules for the problem at hand.' },
];

/**
 * Substitutions taken verbatim from HUMANIZATION_RULES (phases/_shared.py),
 * which is appended to the synthesis prompt that closes every run, to the
 * direct-answer prompts, and to every writing and article phase. Two category
 * rules, two filler cuts, and the specificity standard — chosen because each
 * one is checkable against the source block rather than being a flavour of it.
 *
 * No count of the rules appears in the copy on purpose: the block is edited by
 * hand and is not part of capabilities.generated.ts, so a figure here would be
 * the one number on the page that could quietly go stale.
 */
const PROSE_TELLS = [
  { tell: 'serves as / stands as', fix: 'is' },
  { tell: 'boasts / features', fix: 'has' },
  { tell: 'in order to', fix: 'to' },
  { tell: 'due to the fact that', fix: 'because' },
  { tell: 'has the ability to', fix: 'can' },
  { tell: 'significantly improved performance', fix: 'cut latency by 40 ms' },
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
            what stops the page reading as a list.

            Holds the viewport so §1 starts at the fold rather than peeking
            above it. min-h rather than h: on a short window the content grows
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
            replaceable part, and saying so here stops §9 reading as an
            afterthought bolted onto a fixed pipeline.

            It sits above §1 because these four stages are the frame the
            twelve sections hang on, and because the four failures it names
            are what the reader arrived carrying. */}
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
            below hold whichever one runs.
          </Body>

          <MechanismDiagram />
        </Section>

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
            VERIFIED is reserved for claims a non-model source can carry: a search result, a
            document you supplied, an executed check. This is a rule, not a prompt: no model is
            consulted when it runs, so no model can talk its way around it.
          </Body>

          <dl className="mt-[var(--space-10)] grid gap-[var(--space-6)] sm:grid-cols-2">
            <div className="border-t border-[var(--border)] pt-[var(--space-4)]">
              <dt className="epistemic-hypothesis pl-[var(--space-3)] font-sans text-[8pt] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
                Hypothesis
              </dt>
              <dd className="mt-[var(--space-3)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                The model asserted it and nothing else backs it. Plausible, reasoned, unconfirmed,
                and never dressed up as more.
              </dd>
            </div>
            <div className="border-t border-[var(--border)] pt-[var(--space-4)]">
              <dt className="epistemic-verified pl-[var(--space-3)] font-sans text-[8pt] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
                Verified
              </dt>
              <dd className="mt-[var(--space-3)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
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
            The constraint is grounded in published work: Buyl et al., <em>npj AI</em>{' '}
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

        {/* ── §3 Ideation ───────────────────────────────────────
            Follows §2 because it is the same argument one level
            down. §2 states the routing rule; this is what that
            separation is worth on the task where a model's defaults
            are most visible — asked for ideas, a model returns the
            ones it would give anyone.

            Copy discipline is tighter here than anywhere else on
            the page, because the honest version is weaker than the
            version that writes itself. The clustering, the merging
            of near-duplicates and the three ratings are a brief
            given to one model, NOT code — no embeddings, no
            similarity threshold, no weighted rank. Do not promote
            them. What is genuinely enforced is the separation of
            models, the mode-collapse check on the generated tail,
            and the use-case gate on development; those are the only
            things below that claim to be rules. */}
        <Section id="brainstorming" marker="§3" name="Ideation">
          <Heading>The model with the ideas does not get to score them.</Heading>
          <Lede>
            Ask a model to brainstorm and it hands you its most probable answers, the same ones it
            would hand anyone. Reasoner asks for the distribution instead: three rounds, five ideas
            a round, each carrying the probability the model itself puts on it. The unlikely tail is
            the point, and a round that comes back entirely safe fails a check in code rather than
            being passed along.
          </Lede>
          <Body>
            The technique is Verbalized Sampling, which treats a model&rsquo;s sameness as a
            sampling problem rather than something to prompt harder against. Every idea arrives
            tagged with how far it reached.
          </Body>

          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-3">
            {IDEA_TIERS.map(({ name, desc }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Generating, pruning, developing, and writing up then run on four models from four
            different labs. The one that merges the near-duplicates and rates what survives for
            feasibility, novelty, and impact is never the one that produced them; the one that
            writes the final answer is a fourth again. Three ideas go through to deep development,
            and a development that will not commit to a concrete use case is sent back for another
            pass.
          </Body>
        </Section>

        {/* ── §4 Image making ───────────────────────────────────
            Sits here because §3 has just established that what a
            request is asking for decides which models see it, and
            images are where that rule is easiest to watch working:
            the family a prompt lands in changes the models, the
            output format and the price.

            The exhibit stays at §10. This section is the mechanism
            and that one is the evidence; collapsing them would
            leave either the four images unexplained or the
            explanation unproven. Every claim below maps to code —
            hypergate/sub_agents/image_model_selector.py (families,
            tier hint, no model names in the prompt),
            infrastructure/llm/image_model_catalogue.py (the
            ranking, one primary per lab, the vector exemption) and
            infrastructure/llm/image_generation.py (fallback
            hand-off, policy rewrite, retry). The family call is the
            only judgement here that a model makes. */}
        <Section id="image-making" marker="§4" name="Image making">
          <Heading>No house model, and no favourite lab.</Heading>
          <Lede>
            An image prompt is read for what it is asking for — a logo, a photograph, a poster, an
            edit of something you supplied — and that reading is what picks the models. The
            classifier never sees a model name, only the capability the picture needs, so nothing
            can be routed to a favourite on reputation.
          </Lede>

          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-3">
            {IMAGE_FAMILIES.map(({ name, desc }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Which model then serves that family is decided in code, with no model in the loop. Each
            candidate ranks itself out of its own identifier — the size word and version number the
            lab published it under — so one listed this morning takes its place with no edit here
            and no opinion about whose house is best. Price is measured from the live catalogue: on
            the budget tier it leads, on the premium tier it only breaks ties.
          </Body>
          <Body>
            Primaries are taken one per lab, and a family too thin to fill the slots widens rather
            than quietly returning fewer. Vector is the one deliberate exception. A single lab
            ships SVG generators, so there diversity loses to format, and you get fewer images
            rather than a raster answering to the name of a vector.
          </Body>
          <Body>
            A refusal is treated as routing rather than as an error. A primary that fails hands off
            to the fallback behind it mid-run, and a content-policy block sends the prompt back to
            be rewritten — the studio&rsquo;s name replaced by a description of the thing you were
            actually after — with the whole selection tried again before anything is returned to
            you as a failure.
          </Body>

          <Aside href="#images">See four labs answer the same prompt →</Aside>
        </Section>
        {/* ── §5 Propagation ────────────────────────────────────── */}
        <Section id="propagation" marker="§5" name="Propagation">
          <Heading>An idea does not get to spread itself here.</Heading>
          <Lede>
            Systems that pass work between models have a failure mode a single model does not.
            Text that persuades one stage to carry it into the next can ride the whole pipeline
            and settle into what the system remembers. Reasoner is built so it has nowhere to
            travel.
          </Lede>
          <Body>
            Every stage that reads outside text (a web page, an earlier model, a recalled memory,
            an API caller) is told in its system prompt that such text is data and never
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

        {/* ── §6 Sycophancy ─────────────────────────────────────────
            Last of the four Mechanism failures because it is the only one
            where the reader is the source of the distortion, and the page
            has spent five sections earning the standing to say so. Every
            Body paragraph below must correspond to a true
            SYCOPHANCY_CONTROLS entry — see MechanismDiagram's stage-03
            comment and tests/test_site_capabilities_sync.py. Do not add a
            paragraph here without adding its detector to
            scripts/update_mindmap_meta.py first. */}
        <Section id="sycophancy" marker="§6" name="Sycophancy">
          <Heading>It is not built to be agreed with.</Heading>
          <Lede>
            Assistants trained on human approval learn that agreement scores well. Across five
            preregistered studies, Ibrahim et al. found sycophantic AI gave no better advice than
            a neutral system. The entire gain was in how understood people felt, and three weeks
            of it left them measurably less satisfied with the people in their lives.
          </Lede>
          {SYCOPHANCY_CONTROLS.noApprovalGradient && SYCOPHANCY_CONTROLS.confidencePenalty && (
            <Body>
              Reasoner has no approval gradient to climb. The signal that decides which models get
              used is built from completion, schema validity, critique score and stress-test
              survival; a rating you give is recorded for you and never reaches it. Every run also
              carries a generator whose only instruction is to find flaws, and the critic
              subtracts a penalty from any answer that states unsupported claims confidently. In
              the arithmetic, honest uncertainty outscores false confidence.
            </Body>
          )}
          {SYCOPHANCY_CONTROLS.noStyleSelector && (
            <Body>
              There is no warmth slider and no personality picker. Offered three unlabelled styles
              in that study, a majority chose the flattering one, and not for its advice. They
              chose it because it was easiest to talk to. Choosing a tone is not a control we
              intend to sell you.
            </Body>
          )}
          {SYCOPHANCY_CONTROLS.directPathEpistemicRules && SYCOPHANCY_CONTROLS.premiseAudit && (
            <Body>
              A stated conclusion is treated as a claim to evaluate, not a premise to build on —
              on the direct-answer path by system prompt, and inside the full pipeline by an
              explicit audit of Phase 1's assumptions. A claim about another person's motives that
              only you supplied cannot be marked verified on your word alone; the destructive
              perspective is instructed to attack exactly those claims, not you.
            </Body>
          )}

          <Aside href="/how-it-works#adjudication">See the penalty on a real score matrix →</Aside>
        </Section>

        {/* ── §7 Voice ─────────────────────────────────
            Sits after the four Mechanism failures rather than among them,
            because it is the only section on the page whose subject is not a
            wrong answer. The prose can be flawless and still read as machine
            output, and that is the objection this answers.

            Copy discipline: the humanization block is a brief given to the
            models, NOT a validator — nothing diffs the finished text against
            it. The third paragraph says so in as many words, and must keep
            saying so. The only enforcement claimed is the article pipeline's
            dedicated style pass (role article_humanize), which is a real
            phase with a real model behind it. No count of the rules appears
            here; see the PROSE_TELLS comment for why. */}
        <Section id="voice" marker="§7" name="Voice">
          <Heading>A model cannot hear how it sounds.</Heading>
          <Lede>
            Machine prose has a fingerprint, and the model producing it is the last thing able to
            notice: significance inflation, vague attribution, the reflexive rule of three,{' '}
            <em>serves as</em> standing in for <em>is</em>. Reasoner does not ask for good writing.
            Every model that writes a sentence you will read is handed the tells by name and told
            not to produce them.
          </Lede>
          <Body>
            The list is Wikipedia&rsquo;s, kept by the editors who clean this prose out of articles
            at volume and had to learn its signatures to do it. It arrives in four groups: the
            words, the openers, the structural tics, and the patterns that fake depth. The same
            block goes into the synthesis that closes a full run, into the instant answers, and
            into every phase of an article, so the standard is not a setting on one method.
          </Body>

          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-2">
            {PROSE_TELLS.map(({ tell, fix }) => (
              <div key={tell} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-subtle)]">
                  <s className="decoration-[var(--border-strong)]">{tell}</s>
                </dt>
                <dd className="mt-[var(--space-1)] font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-2)]">
                  <span aria-hidden="true" className="text-[var(--text-subtle)]">&rarr;{' '}</span>
                  {fix}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            A brief is not a validator, and nothing checks the finished text against the list
            afterwards. What an article run adds is a phase whose only job is the tells that got
            through: an editor model quotes each one it can find in the draft, then rewrites the
            piece without them. Ask for a particular author or publication and that pass is told to
            keep the voice rather than flatten the piece into a neutral register.
          </Body>

          <Aside href="#writing">See the run that pass belongs to &rarr;</Aside>
        </Section>

        {/* ── §8 Research ───────────────────────────────────────── */}
        <Section id="research" marker="§8" name="Research">
          <Heading>It searches like a researcher, not a search box.</Heading>
          <Lede>
            A single query returns what the query deserved. Reasoner runs an agentic loop that
            picks its own next move each iteration, goes broad before it goes narrow, and decides
            for itself when it has enough.
          </Lede>

          <ol
            role="list"
            className="mt-[var(--space-8)] grid list-none gap-[var(--space-4)] font-mono text-[13pt] leading-[var(--lh-body)]"
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
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Aside href="/how-it-works#evidence">See what one run actually read →</Aside>
        </Section>

        {/* ── §9 Methods ────────────────────────────────────────── */}
        <Section id="methods" marker="§9" name="Methods">
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
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Each ships in a budget and a premium tier, for {CAPABILITIES.presets} routing
            configurations in total, spanning {CAPABILITIES.routableModels.toLocaleString('en-US')}{' '}
            routable models. You can pick one, or let the router pick from the question.
          </Body>

          <Aside href="/docs">Read the method reference →</Aside>
        </Section>

        {/* ── §10 Images ─────────────────────────────────────────── */}
        <Section id="images" marker="§10" name="Images">
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
              refuses is §4's argument; repeating it here would make the page
              claim the same mechanism twice and leave the exhibit doing the
              explaining. This paragraph carries only what §4 does not: the
              controls a reader gets to hold. */}
          <Body>
            Reference images, five aspect ratios, and automatic prompt enhancement come as
            standard. Which four models answered this one, and what happens when one of them
            refuses, is the routing described earlier.
          </Body>

          <Aside href="#image-making">See how these four were picked →</Aside>
        </Section>

        {/* ── §11 Writing ────────────────────────────────────────── */}
        <Section id="writing" marker="§11" name="Writing">
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
            Phase seven is the style pass described further up the page, run here against a
            finished draft rather than a first answer. Sources are assembled from the links
            actually present in that draft, so the bibliography describes the article rather than
            the intention.
          </Body>
        </Section>

        {/* ── §12 Code ──────────────────────────────────────────
            Brainstorming used to open this section, which left it
            trying to carry ideation and code in two sentences and
            serving neither. Ideation now has §3; this says the one
            thing about code worth the space. */}
        <Section id="code" marker="§12" name="Code">
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
