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
 * sections; it now lives at /capabilities, with its anchors intact. What stays
 * here is the claim, the four-stage rail that frames it, and the exhibits — a
 * real image run, a real article run, and the ideation tiers — because those
 * are the parts a first-time reader can check without being asked to read an
 * essay first.
 *
 * Ideation (§3) came back from /capabilities on that test: it is an exhibit,
 * not an essay. Its `brainstorming` anchor moved with it, so the numbering at
 * /capabilities closed up while every id on both pages stayed put.
 *
 * Copy discipline: every figure comes from `capabilities.generated.ts`, which
 * is regenerated from the live registry on each commit. Nothing here is typed
 * by hand, and nothing claims enforcement the code does not perform — see
 * docs/plans/landing-capability-pivot.md §3 for the claim-to-code table.
 */

/* ── Content ────────────────────────────────────────────── */

/**
 * The two image tiers, as core/constants_limits.py configures them
 * (IMAGE_GEN_BUDGET_MODELS / IMAGE_GEN_PREMIUM_MODELS). Both field four
 * models from four different labs and both cross a bloc boundary; the tier
 * decides which model each lab sends, never how many labs answer. Hand-kept
 * against those two lists — the only place on the home page that names a
 * model's lab, because "premium" means nothing until a reader can see what
 * it actually swaps.
 */
const IMAGE_TIERS = [
  {
    name: 'Budget',
    badge: 'Default',
    note: 'The four cheapest capable models in the catalogue, one per lab, ranked on measured price rather than on reputation.',
    labs: [
      { lab: 'Black Forest Labs', origin: 'Germany' },
      { lab: 'Krea', origin: 'United States' },
      { lab: 'Sourceful', origin: 'United States' },
      { lab: 'ByteDance', origin: 'China' },
    ],
  },
  {
    name: 'Premium',
    badge: 'One toggle away',
    note: 'The same four-lab rule with each lab’s strongest image model instead. Switch tier in the composer; nothing else about the run changes.',
    labs: [
      { lab: 'OpenAI', origin: 'United States' },
      { lab: 'Google', origin: 'United States' },
      { lab: 'Recraft', origin: 'United States' },
      { lab: 'ByteDance', origin: 'China' },
    ],
  },
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

        {/* ── Images ─────────────────────────────────────────────
            Runs without a marginal column. The four images ARE the
            argument here, and the 9rem label track was costing them a
            ninth of the measure to repeat a word the heading already
            says. Full width also lets the plates sit four-up at a size
            where the differences between labs are actually visible,
            which is the entire point of showing four.

            Two things the reader must leave with, in this order: four
            images come back from four different labs on every run, and
            the premium tier is a toggle rather than a different
            product. The tier panels below carry the second — they are
            the only place on this page that names models, because
            "premium" means nothing until you can see what changes. */}
        <Section id="images">
          <Heading>Every prompt goes to four labs at once.</Heading>
          <Lede>
            One prompt, four models, four different labs, generating in parallel. No single house
            style, outage, or content refusal decides what comes back, and every primary has a
            fallback behind it. The four below are one real run, left as it happened.
          </Lede>

          <figure className="mt-[var(--space-10)]">
            <p className="font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              &ldquo;{SHOWCASE_PROMPT}&rdquo;
            </p>

            <ul
              role="list"
              className="mt-[var(--space-6)] grid list-none gap-[var(--space-5)] grid-cols-2 lg:grid-cols-4"
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

            <figcaption className="mt-[var(--space-5)] font-sans text-[8pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              <span aria-hidden="true">†</span> Two of the configured primaries failed on this run
              and fallbacks took over mid-flight. Left as it happened. A chain you can watch
              working is worth more than one you have to take on faith.
            </figcaption>
          </figure>

          {/* The tier is a swap of which model each lab sends, never a
              change to how many labs answer. Saying that in the header
              above the panels stops the cheaper tier reading as the
              crippled one, which is what a bare feature table would do. */}
          <div className="mt-[var(--space-16)] border-t border-[var(--border-strong)] pt-[var(--space-6)]">
            <h3 className="font-serif text-[21pt] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
              Four labs either way. The tier picks which model each one sends.
            </h3>

            <div className="mt-[var(--space-8)] grid gap-[var(--space-10)] sm:grid-cols-2">
              {IMAGE_TIERS.map(({ name, badge, note, labs }) => (
                <div key={name}>
                  <div className="flex flex-wrap items-baseline gap-x-[var(--space-3)] gap-y-[var(--space-1)]">
                    <h4 className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                      {name}
                    </h4>
                    <span className="font-mono text-[8pt] uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--accent)]">
                      {badge}
                    </span>
                  </div>
                  <p className="mt-[var(--space-2)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                    {note}
                  </p>
                  <ul role="list" className="mt-[var(--space-4)] list-none">
                    {labs.map(({ lab, origin }) => (
                      <li
                        key={lab}
                        className="flex items-baseline justify-between gap-[var(--space-4)] border-t border-[var(--border)] py-[var(--space-2)]"
                      >
                        <span className="font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-2)]">
                          {lab}
                        </span>
                        <span className="font-mono text-[8pt] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
                          {origin}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>

          {/* Deliberately does NOT restate the routing. Which four models
              answered, why they came from four labs, and what happens when one
              refuses is /capabilities §4's argument; repeating it here would
              make the page claim the same mechanism twice and leave the
              exhibit doing the explaining. This paragraph carries only what
              that section does not: the controls a reader gets to hold. */}
          <Body>
            Reference images, five aspect ratios, and automatic prompt enhancement come as
            standard on both tiers. Which four models answered this one, and what happens when one
            of them refuses, is the routing described under{' '}
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

        {/* ── §3 Ideation ───────────────────────────────────────
            Lives here rather than with the rest of the mechanism
            argument at /capabilities, because it passes the test
            everything on this page has to pass: the three tiers are
            an exhibit, something to look at, and the claim above
            them is checkable in a sentence without the surrounding
            essay. Its anchor stayed `brainstorming` through the
            move, so the id is stable even though the page it hangs
            on is not — an old /capabilities#brainstorming link now
            lands on that page with nothing to scroll to, which is
            the one cost of the move and worth a redirect if those
            links turn out to exist anywhere public.

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

          <Aside href="/capabilities#bias">Why a different lab is the one scoring →</Aside>
        </Section>

        {/* ── §4 Code ───────────────────────────────────────────
            Brainstorming used to open this section, which left it
            trying to carry ideation and code in two sentences and
            serving neither. Ideation is §3 above; this says the one
            thing about code worth the space. */}
        <Section id="code" marker="§4" name="Code">
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
