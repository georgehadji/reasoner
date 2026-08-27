import Link from 'next/link';
import { DisagreementField } from '@/components/landing/DisagreementField';
import { MechanismDiagram } from '@/components/landing/MechanismDiagram';
import { Aside, Body, Heading, Lede, Section } from '@/components/landing/prose';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, PROVIDERS } from '@/lib/capabilities.generated';
import { CLAIM_SPECIMENS } from '@/lib/demo-record';
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

/**
 * The three driving adapters an agent can come through, ordered by how little
 * code each costs the caller. Every claim here is checkable: the MCP tools are
 * in src/reasoner/api/mcp/tools.py, the bearer-key endpoints in
 * api/routes/agent.py, and the CLI and in-process entry points are main.py and
 * reasoner.headless.ask().
 */
const AGENT_DOORS = [
  {
    name: 'MCP',
    detail:
      'Six tools, one config block, no client code. Claude Desktop, Claude Code and most agent frameworks pick it up and show progress phase by phase.',
  },
  {
    name: 'HTTP',
    detail:
      'One authenticated POST. Take the finished result as JSON, or stream the phases as they land. Tool definitions are served live, never copied.',
  },
  {
    name: 'CLI',
    detail:
      'A shell or a cron job, written out as JSON — or the pipeline imported in-process, with no server standing between you and it.',
  },
];

/**
 * Rule style per label, from the utilities in globals.css. Fill AND rule
 * pattern carry the same information, so the three stay distinguishable in
 * monochrome and to a colour-blind reader.
 */
const CLAIM_RULE: Record<string, string> = {
  VERIFIED: 'epistemic-verified',
  HYPOTHESIS: 'epistemic-hypothesis',
  UNKNOWN: 'epistemic-unknown',
};

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

            Two things the reader must leave with: four images come
            back from four different labs on every run, and the premium
            tier is a toggle rather than a different product. Both live
            in the one paragraph below, which is deliberately the whole
            of the prose here — the plates are the argument, and a
            reader who stops after the heading has still been told the
            thing that matters.

            Do NOT list the tier line-ups. Naming the models each
            preset fields dates the page against constants_limits.py
            and turns a claim about how the run is composed into a spec
            sheet a competitor can shop against. */}
        <Section id="images">
          <Heading>Every prompt goes to four labs at once.</Heading>
          <Lede>
            One prompt, four models, four different labs, generating in parallel, so no single
            house style, outage, or content refusal decides what comes back, and every primary has
            a fallback behind it. The tier changes which model each lab sends, never how many labs
            answer: budget runs by default on the cheapest capable model in the catalogue, ranked
            on measured price rather than on reputation, while premium is one toggle away in the
            composer and takes each lab&rsquo;s strongest instead. Reference images, five aspect
            ratios, and automatic prompt enhancement come as standard on both. The four below are
            one real run; which models answered it, and what happens when one of them refuses, is
            the routing described under{' '}
            <Link
              href="/capabilities#image-making"
              className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              image making
            </Link>
            .
          </Lede>

          <figure className="mt-[var(--space-10)]">
            <p className="font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              &ldquo;{SHOWCASE_PROMPT}&rdquo;
            </p>

            <ul
              role="list"
              className="mt-[var(--space-6)] grid list-none gap-[var(--space-5)] grid-cols-2 lg:grid-cols-4"
            >
              {SHOWCASE_IMAGES.map(({ src, model, lab, origin }) => (
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
                  </p>
                  <p className="mt-[var(--space-1)] font-mono text-[8pt] leading-[var(--lh-body)] text-[var(--text-subtle)]">
                    {model} · {origin}
                  </p>
                </li>
              ))}
            </ul>
          </figure>
        </Section>

        {/* ── §1 Writing ─────────────────────────────────────────── */}
        <Section id="writing" marker="§1" name="Writing">
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

        {/* ── §2 Ideation ───────────────────────────────────────
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
        <Section id="brainstorming" marker="§2" name="Ideation">
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

        {/* ── §3 Code ───────────────────────────────────────────
            Brainstorming used to open this section, which left it
            trying to carry ideation and code in two sentences and
            serving neither. Ideation is §2 above; this says the one
            thing about code worth the space. */}
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

        {/* ── §4 Agents ─────────────────────────────────────────
            Last of the numbered sections because it is the only one
            whose reader is not a person typing a question.

            It obeys the same test as the rest of the page: exhibit,
            not essay. The specimens are three real labelled claims
            pulled out of the captured run by CLAIM_SPECIMENS, so this
            section shows the thing an integrator is buying — a
            machine-readable verdict — rather than describing it. They
            are derived, never transcribed: nothing here can quote a
            claim the run did not make.

            The three doors are the argument: MCP (api/mcp/tools.py),
            the bearer-key HTTP surface (api/routes/agent.py), and the
            CLI and in-process module (main.py, headless.ask) all enter
            the same application layer. Do not describe a capability
            here that holds on only one of them.

            Install, the six tool names, idempotency and status codes
            belong at /developers and /docs/mcp. This section makes the
            case and hands off. */}
        <Section id="agents" marker="§4" name="Agents">
          <Heading>Your agent does not have to take a model&rsquo;s word for it.</Heading>
          <Lede>
            Ask one model and you get prose, plus the job of deciding how much of it to believe.
            Ask this and the answer arrives sorted: what a source outside the model carries, what
            the run is only proposing, and what nothing settled. Three labels your code can branch
            on, from an answer that had to survive being argued with first.
          </Lede>

          {/* Real output, not an illustration of one. */}
          <dl className="mt-[var(--space-10)] space-y-[var(--space-5)]">
            {CLAIM_SPECIMENS.map(({ claim, label, qualifier }) => (
              <div key={label} className="border-t border-[var(--border)] pt-[var(--space-4)]">
                <dt
                  className={`${CLAIM_RULE[label]} pl-[var(--space-3)] font-sans text-[8pt] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]`}
                >
                  {label}
                  {qualifier ? (
                    <span className="font-normal normal-case tracking-normal text-[var(--text-subtle)]">
                      {' '}
                      {qualifier}
                    </span>
                  ) : null}
                </dt>
                <dd className="prose-measure mt-[var(--space-2)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {claim}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Those three are lifted out of{' '}
            <Link
              href="/how-it-works"
              className="link-smooth text-[var(--accent)] hover:text-[var(--accent-hover)]"
            >
              one captured run
            </Link>
            , with its labelling untouched. An agent gets them as fields rather than as prose:
            the claims and their labels, the questions the run could not close, and a plan whose
            every step carries the criterion that says whether it worked.
          </Body>

          <dl className="mt-[var(--space-10)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-3">
            {AGENT_DOORS.map(({ name, detail }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Three doors, one pipeline. A run started from Claude Desktop resolves credentials,
            guards against a duplicate and settles against the same ledger as one started from
            curl — there is no second product with its own accounting. And two of the calls are
            free: one tells you which method a question would get, the other what it would cost,
            so an agent can look before it spends.
          </Body>
          <Body>
            {/* The direct MCP link is deliberate and load-bearing: this
                section is where a crawling agent reads that Reasoner is
                callable, and the next thing it needs is the setup page, not
                another essay. Keep an inline link to /docs/mcp here. */}
            Setup is one dependency and a config block —{' '}
            <Link
              href="/docs/mcp"
              className="link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]"
            >
              add the MCP server to your host
            </Link>
            .
          </Body>

          <Aside href="/developers">The developer surface, in full →</Aside>
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
