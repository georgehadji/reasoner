import Link from 'next/link';
import { DisagreementField } from '@/components/landing/DisagreementField';
import { MechanismDiagram } from '@/components/landing/MechanismDiagram';
import { Aside, Body, Heading, Lede, Section } from '@/components/landing/prose';
import { ReviewHandoff } from '@/components/landing/ReviewHandoff';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { LogoLoop } from '@/components/ui/LogoLoop';
import { CAPABILITIES, MARQUEE_LABS, PROVIDERS } from '@/lib/capabilities.generated';
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
 * Ideation came back from /capabilities on that test: it is an exhibit, not
 * an essay. It carries no marker/name — the first thing on the page after the
 * masthead should not compete with the masthead for a section number — but
 * kept its `brainstorming` anchor, so old #brainstorming links still resolve.
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
 * Sampling rounds (phases/brainstorming.py) — internally a probability the
 * model assigns its own output, but the copy sells the shelf, not the gauge:
 * this is what comes back, not the mechanism that sorted it.
 */
const IDEA_TIERS = [
  {
    name: 'Conventional',
    desc: 'The safe answer. Worth having on record — never worth stopping at.',
  },
  {
    name: 'Lateral',
    desc: 'Structure borrowed from a domain this problem has never been put next to.',
  },
  {
    name: 'Disruptive',
    desc: 'The one a single prompt would never have handed you.',
  },
];

/**
 * Where each marquee lab is headquartered.
 *
 * The masthead claims rival labs *and rival geopolitical blocs*. A reader can
 * check the first half by recognising the names; the second half is the part
 * that needs saying, and it is the half no competitor's logo strip can copy.
 *
 * Keyed off `MARQUEE_LABS` rather than restating it, so a lab added to
 * capabilities.generated.ts by scripts/update_mindmap_meta.py appears in the
 * strip on the next commit. An unmapped one renders as a bare wordmark — a
 * missing origin is a gap, a guessed one is a false claim, and this page's
 * whole argument is that it does not make those.
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
              <p className="prose-measure text-[21pt] leading-[1.6] text-[var(--text-2)]">
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

          {/* The lede's one unverifiable-sounding phrase, made checkable:
              rival labs, and the countries they answer to.

              Names only — no logos. Every wordmark here is a trademark we
              have no licence to reproduce, the CSP forbids a third-party
              image host anyway, and set in the page's own type the strip
              reads as a list of facts rather than a wall of borrowed brands.

              Below the price line rather than above the buttons: this is
              evidence for a reader who has already decided to be sceptical,
              and putting a moving element between the claim and the call to
              action taxes everyone else to serve them.

              Measured, it lands under the fold on a 900px-tall viewport — as
              the price line above it already did, since the masthead's
              content has been taller than `min-h-svh` for a while. So it is
              the first thing scrolling reveals, not something the reader
              meets beside the headline. That is still the right place for it;
              it is not the place to claim otherwise. */}
          <div className="relative mt-[var(--space-12)]">
            <LogoLoop
              ariaLabel="Model labs Reasoner routes to, with the country each lab is based in"
              items={MARQUEE_LABS.map((name) => (
                <span key={name} className="flex items-baseline gap-[var(--space-2)]">
                  <span className="font-sans text-[13pt] font-medium leading-[var(--lh-ui)] text-[var(--text-2)]">
                    {name}
                  </span>
                  {LAB_ORIGIN[name] ? (
                    <span className="font-sans text-[8pt] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                      {LAB_ORIGIN[name]}
                    </span>
                  ) : null}
                </span>
              ))}
            />
          </div>
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

        {/* ── Writing ────────────────────────────────────────────
            Runs without a marginal column, like Images. The nine-step
            list IS the label: a 9rem track repeating the word "writing"
            beside an ordered sequence of named phases spends a ninth of
            the measure saying what the reader can already see. The two
            sections that keep their markers are the ones whose content
            does not announce itself.

            The one section on this page written to a reader with money
            at stake, because this is the one capability people are paid
            for. It is also the only section competing in a market that
            has heard every claim: the humaniser category sells
            "undetectable" and "100% bypass", the detectors retrain
            against it, and the reader has already been burned. Matching
            that claim would put us in the same sentence as the tools
            that fail it.

            So the section refuses the category's frame instead. The
            detector is not the gate that pays; an editor is. That
            reframing is the whole heading, and it lets the mechanism
            below do the persuading, which is the only move left in a
            market this sophisticated.

            Two constraints, both easy to break by accident:

            1. Do NOT claim undetectable, human-indistinguishable, or
               anything about passing a detector. It is unprovable, it
               dates the moment a detector ships, and it is the exact
               claim this section is positioned against.
            2. Do NOT re-argue voice. §6 at /capabilities owns the tells
               argument and states honestly that the brief is not a
               validator. This section shows the one thing an ARTICLE
               run adds on top: a phase that quotes the tells still
               standing, then rewrites without them. Contradicting or
               duplicating §6 costs us the credibility both pages are
               built on.

            Prose here also avoids em-dashes, which the same reader now
            reads as a machine signature. A section promising prose that
            does not sound generated cannot be punctuated like the thing
            it is arguing against.

            GROUND TRUTH, audited 2026-08-27 against the article flow.
            Four claims that had stood here were false. Three were then
            made true in code rather than deleted; one stays deleted.

            FIXED, so the claim is now allowed:
            - The tell-quoting humanize pass. writing_humanize_prompt had
              zero call sites; article phase 6a ran ARTICLE_STYLE_EDIT_SYSTEM
              instead, five bullets with no tell list. Phase 6a now runs
              WRITING_HUMANIZE_SYSTEM (flows/article_phases.py), which must
              quote each tell before rewriting, with the old prose pass kept
              as the parse-failure fallback. Needed article_humanize: 8192 in
              PHASE_TOKEN_BUDGETS, because it returns the whole article
              inside a JSON string and 2048 truncated it mid-object.
            - HUMANIZATION_RULES on the article body. It reached only the
              phase 8 synthesis. Now appended to ARTICLE_DRAFT_SYSTEM.
              Draft ONLY: the developmental edit is told not to touch voice
              or register and the copy edit not to change word choice, so
              the same rules there contradict the prompt they hang on.
            - Sources from the links actually in the text. The deterministic
              extraction existed only in the writing flow; the article flow
              now imports the same helper and appends ## Sources.
            - The audit retry, which was real but CLI-only, because the SSE
              driver never calls ArticleFlow.execute(). It now lives inside
              run_article_final_audit_phase, so every driver gets it, and
              the second failure is recorded to state.errors instead of
              shipping silently.

            STILL FALSE, do not write these:
            - "The fact-check is a hard gate." Deliberate. Every article
              PhaseStep is critical=False, and a low claim-support ratio
              logs and writes gaps_noted. Advisory by product decision:
              the reader gets a usable draft with the holes marked, not a
              dead run they already paid phases for. Say labelled, never
              gated.
            - Author or publication voice matching. style_brief is written
              by tests and nothing else, there is no API field for it, and
              /capabilities §5 says a tone control is not something we
              intend to sell. Offering it here would contradict that.

            Nothing below is a validator, and the last paragraph says so.
            Keep it saying so. */}
        <Section id="writing">
          <Heading>It has to survive an editor, not a detector.</Heading>
          <Lede>
            Nobody pays for a draft that passes a detector. They pay for one that does not come
            back. So an article here is not one generation. It moves through nine phases, each on
            its own model, and the one that writes the draft is never the one that fact-checks it,
            never the one that cuts it, and never the one that signs off the final audit.
          </Lede>

          {/* One column, not three. These are nine steps in a fixed order and
              a multi-column grid makes the reader work out the reading
              direction before they can see the sequence. Stacked, the order is
              the shape. */}
          <ol role="list" className="mt-[var(--space-8)] grid list-none gap-[var(--space-3)]">
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
            Phase four is adversarial by instruction. A model from another lab is told to assume
            the draft invented its statistics and misattributed its quotes, and to rate every
            claim it makes verified, supported, partial, speculative, or unsupported. That ledger
            is handed to the final audit rather than being formed again by impression, and the
            draft before it is told to mark a claim it cannot source UNVERIFIED instead of
            smoothing over it.
          </Body>

          <Body>
            Phase seven decides how it reads, on a model of its own again. It has to quote the
            machine-prose{' '}
            <Link
              href="/capabilities#voice"
              className="link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]"
            >
              tells
            </Link>{' '}
            it can find in the draft before it is allowed to rewrite, because a model asked only
            to sound more human reaches for synonyms, while one made to name the pattern first has
            to deal with the sentence it just quoted. The same banned constructions go into the
            drafting prompt, so most of them are never written.
          </Body>

          <Body>
            A piece that fails the final audit is edited again and re-audited before anyone sees
            it, and if it fails twice that is recorded rather than quietly shipped. Sources are
            assembled from the links actually present in the finished text, so the bibliography
            describes the article rather than the intention. None of that is a validator: nothing
            diffs the published text against the list afterwards. It is a brief given to models,
            and a page arguing for checkable claims is the wrong place to pretend otherwise.
          </Body>
        </Section>

        {/* ── Images ─────────────────────────────────────────────
            Runs without a marginal column. The four images ARE the
            argument here, and the 9rem label track was costing them a
            ninth of the measure to repeat a word the heading already
            says. 2x2 rather than 4-up: at this width four-across shrinks
            each plate below the size where a house style actually reads,
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
          {/* The name of the capability, since nothing else here says it.
              Dropping the marginal column bought the plates the full measure
              but cost the section its label, and a reader arriving at four
              photographs under a heading about labs has been shown the
              product without being told what it is. Same 8pt uppercase spec
              the marginal column uses, so it is the page's own label idiom
              moved inline rather than a second one invented for this
              section. */}
          <p className="font-sans text-[8pt] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
            Image generation
          </p>

          <div className="mt-[var(--space-6)] grid gap-x-[var(--space-12)] gap-y-[var(--space-6)] lg:grid-cols-2 lg:items-end">
            {/* One step up from the shared Heading (34pt): this section leads
                the page's exhibits and the display size is what makes the
                two-column split read as a masthead rather than as a caption. */}
            <h2 className="font-serif text-[34pt] sm:text-[55pt] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
              Every prompt goes to four labs at once.
            </h2>
            <p className="text-[21pt] leading-[var(--lh-body)] text-[var(--text-2)]">
              Write one prompt and four labs answer it at once, so you pick between four takes
              instead of arguing with one. Reference images, five aspect ratios and prompt
              enhancement come as standard. Premium is one toggle in the composer: still four
              labs, each sending its best.
            </p>
          </div>

          <figure className="relative mt-[var(--space-10)]">
            {/* The light the tilt implies. Four plates leaning back off a
                shared vanishing point need a source above them, or the
                rotation reads as a rendering glitch rather than as an object
                being lit. Static gradient on an existing theme token — no
                canvas, no loop, nothing to pause off-screen. Painted first
                and never given a z-index: the plates are opaque and come
                later in the DOM, so they cover it without a stacking
                context being invented for the section. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-[-8%] top-[10%] h-[55%] bg-[radial-gradient(ellipse_at_top,var(--accent-dim),transparent_70%)]"
            />

            <p className="font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              &ldquo;{SHOWCASE_PROMPT}&rdquo;
            </p>

            {/* Perspective on the grid, not on each plate — one shared
                vanishing point is what makes four tilted squares read as one
                object seen at an angle instead of four cards that each warped
                alone. Same depth language and same numbers as
                MechanismDiagram; the page should only own one. */}
            <ul
              role="list"
              className="mt-[var(--space-6)] grid list-none grid-cols-2 gap-[var(--space-5)] [perspective:1400px]"
            >
              {/* Lab name only. Model id and country stay in the showcase data
                  and in manifest.json as the run's provenance, but neither is
                  shown: the id dates the page the moment a tier is re-ranked,
                  and the country is an argument this page is not making here.
                  The claim is which HOUSE answered. */}
              {SHOWCASE_IMAGES.map(({ src, lab }) => (
                <li
                  key={src}
                  className="plate-reveal card-hover group [transform-style:preserve-3d] hover:[transform:translateZ(26px)_rotateX(3.5deg)] motion-reduce:hover:[transform:none]"
                >
                  {/* Held slightly under-saturated at rest and released on
                      hover. Four photographs at full colour side by side
                      fight each other; pulling them back a notch makes the
                      grid read as one exhibit and makes the one you are
                      pointing at the only one at full strength. Filter only —
                      a scale here would need overflow:hidden, and that forces
                      transform-style back to flat and kills the tilt. */}
                  <img
                    src={src}
                    alt={`${lab}'s interpretation of the prompt: a street food stall at dusk in heavy rain, lit by one bare bulb, steam rising off the griddle`}
                    width={720}
                    height={720}
                    loading="lazy"
                    decoding="async"
                    fetchPriority="low"
                    sizes="(max-width: 768px) 45vw, 30vw"
                    className="aspect-square w-full border border-[var(--border)] object-cover saturate-[0.9] transition-[filter,border-color] duration-[var(--dur-component)] ease-[var(--ease-standard)] group-hover:border-[var(--border-strong)] group-hover:saturate-100"
                  />
                  <p className="mt-[var(--space-3)] font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                    {lab}
                  </p>
                </li>
              ))}
            </ul>
          </figure>
        </Section>

        {/* ── Ideation ────────────────────────────────────────────
            Lives here rather than with the rest of the mechanism
            argument at /capabilities, because it passes the test
            everything on this page has to pass: the three tiers are
            an exhibit, something to look at, and the claim above
            them is checkable in a sentence without the surrounding
            essay. No marker/name — the first thing after the
            masthead should not compete with the masthead for a
            section number. Kept the `brainstorming` id through
            every move, so old #brainstorming links still resolve.

            Deliberately not a mechanism explainer. The brief from
            this section's last review still holds — the clustering,
            the merging of near-duplicates and the three ratings are
            given to one model, NOT code, so do not promote them as
            enforced — but the standing instruction on TOP of that is
            to not walk the reader through process at all (rounds,
            counts, gates). Name what is genuinely advanced —
            Verbalized Sampling, four models across four labs, a
            code-level mode-collapse check — as credibility, and stop
            there. Anyone who wants the mechanism has the Aside link
            to the full essay. Copy sells the shelf, not the gauge:
            see IDEA_TIERS above for the same rule applied to the
            tier descriptions. */}
        <Section id="brainstorming">
          <Heading>Your best idea is the one it almost didn&rsquo;t say.</Heading>
          <Lede>
            Ask a model to brainstorm and it hands you the answer built to please &mdash; the same
            safe idea it would give the next person who asked.
          </Lede>
          <Body>
            Reasoner is engineered to get past that reflex. Verbalized Sampling reaches outside a
            model&rsquo;s own habits instead of asking it to try harder. Four models from four
            different labs mean no single lab&rsquo;s taste decides what survives. And a check
            written into the code &mdash; not a prompt &mdash; refuses a batch of ideas that comes
            back entirely safe.
          </Body>

          <dl className="mt-[var(--space-4)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-3">
            {IDEA_TIERS.map(({ name, desc }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-sans text-[13pt] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            The model that had the ideas is never the one that scores them. A different lab decides
            what survives &mdash; every time, not by exception.
          </Body>

          <Aside href="/capabilities#bias">Why a different lab is the one scoring →</Aside>
        </Section>

        {/* ── Code ──────────────────────────────────────────────
            Was three sentences and a §2 marker. The marker went with
            the marginal column: Ideation above it dropped its own in
            an earlier pass, so a lone §2 was numbering a sequence that
            no longer existed, and the exhibit wanted the 9rem back.
            Labelled inline instead, the same way Images is.

            THE WEDGE, and the only reason this section exists. Every
            coding assistant on the market ships code that the model
            which wrote it has just told you looks fine. One model,
            author and reviewer, marking its own homework. Splitting
            those two across labs is the one thing here a competitor
            cannot also claim, so it is the heading, the lede and the
            drawing, and everything else is support.

            Do NOT reach for the obvious second claim. This section is
            positioned against single-model assistants, not against
            human review, and copy that implies the reviewer replaces
            an engineer would be the same overreach the writing
            section refuses when it declines to promise a detector
            bypass.

            GROUND TRUTH, verified 2026-08-27 against the coding flow.
            The full claim-to-code table is in lib/code-showcase.ts and
            is the thing to read before editing a word of this. The
            three that are easiest to overstate by accident:

            - Security Review is the one phase built with critical=True
              (flows/coding.py:43) and the SSE path really does honour
              it (api/execution/pipeline.py:311,427,467), unlike the
              article flow where every step is critical=False. But it
              is a phase-FAILURE gate. It stops a run whose review did
              not complete, NOT a run whose review found problems.
              "Nothing ships until the review passes" is a lie.
            - Author lab ≠ reviewer lab is how both coding presets are
              routed (preset_registry.py:728-761,766-772), and it is
              NOT enforced: BlocDiversityConstraint's _GENERATOR_ROLES
              does not list coding_generate. Say the presets route it
              that way. Never "by rule" — that phrase is the
              masthead's promise about epistemic labels and is load-
              bearing everywhere else on this page.
            - Tests are generated, not run. The prompt tells them to
              cover what the review flagged (phases/coding.py:219-225),
              which is the real and sufficient claim. Contract
              validation commands DO reach the sandbox
              (flows/coding_phases.py:200-216) but only when the spec
              emitted any, so it cannot be stated unconditionally.

            The PoT sandbox line survives from the old copy because it
            is still true and still checkable: NoopExecutor is
            installed rather than None precisely so a phase can never
            fall back to letting an LLM narrate an execution it did not
            perform (flows/services.py:26-43). */}
        <Section id="code">
          <p className="font-sans text-[8pt] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
            Code generation
          </p>

          <div className="mt-[var(--space-6)]">
            <Heading>Written by one lab. Attacked by another.</Heading>
          </div>

          {/* "Most assistants", not "every assistant". The claim is about the
              default arrangement, which is fair and checkable; an absolute
              quantifier over every product on the market is one a competitor
              could break with a single counter-example, and this page cannot
              afford to be caught out on a number or a scope. */}
          <Lede>
            On most assistants the model that wrote your code is the same one that tells you it
            looks fine. Author and reviewer, one model, marking its own homework. Here they are
            two: the file is written by one model, then handed to a different one from a different
            lab, briefed as a hostile reviewer and told to find every flaw before you see it.
          </Lede>

          <Body>
            That reviewer is not working from memory either. Before it reads a line, Reasoner
            searches for known vulnerabilities and hardening guidance for the exact language and
            framework your spec named, and hands those references to the review along with the
            code. What comes back is not a verdict, it is a list: severity, file, line, and the
            fix. The test suite is written last, on a third model, and is told to cover the issues
            the review just raised.
          </Body>

          <ReviewHandoff />

          <Body>
            Of the seven phases, the security review is the only one the run cannot skip past &mdash;
            a review that fails to complete ends the run rather than letting the code through
            unread. And where a step reasons in code rather than prose, that code is executed in a
            sandbox under a wall-clock limit and a memory cap. When the sandbox is off, the phase
            is refused outright. It is never handed to a model to narrate an execution that never
            happened.
          </Body>

          {/* "All n", not "the other n" — coding is one of the n, and an
              off-by-one is exactly the kind of thing this page is read for. */}
          <Aside href="/capabilities#methods">
            All {CAPABILITIES.methods} reasoning methods &rarr;
          </Aside>
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
                <dd className="prose-measure mt-[var(--space-2)] text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {claim}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Those three are lifted out of{' '}
            <Link
              href="/how-it-works"
              className="link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]"
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
                <dd className="mt-[var(--space-1)] text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
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
                <dd className="mt-[var(--space-1)] text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-[var(--space-8)] font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            Routes across {PROVIDERS.join(', ')}, and{' '}
            {CAPABILITIES.routableModels.toLocaleString('en-US')} models through OpenRouter. Full
            detail in{' '}
            <Link href="/security" className="link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]">
              security
            </Link>
            ,{' '}
            <Link href="/privacy" className="link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]">
              privacy
            </Link>
            , and{' '}
            <Link
              href="/subprocessors"
              className="link-smooth text-[var(--accent)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent-hover)]"
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
