import Link from 'next/link';
import { Aside, Body, Heading, Lede, Section } from '@/components/landing/prose';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, SYCOPHANCY_CONTROLS } from '@/lib/capabilities.generated';

/**
 * The mechanism argument, in eight parts.
 *
 * These sections used to run down the home page. They were moved here because
 * the home page has one job — state the claim, show the product's own output,
 * ask for the click — and nine sections of mechanism between the masthead and
 * the exhibits buried both. The anchors and the copy survived that move
 * unchanged, so an inbound link to #sycophancy still lands on the section it
 * was written for, one URL over.
 *
 * Ideation (#brainstorming) has since gone back to the home page: its three
 * tiers are an exhibit rather than an essay, which is the test that page
 * applies. The §n markers here closed up over the gap it left, so the marker a
 * section carries is no longer the one it had on the home page. The anchors did
 * not move, and they are what links are written against — never renumber by
 * changing an id.
 *
 * Every section is the same claim from a different angle: Reasoner runs work
 * past models that disagree, then makes the disagreement part of the output.
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

/* ── Page ─────────────────────────────────────────────────────────── */

export default function CapabilitiesPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead ───────────────────────────────────────────
            Short on purpose. A reader who arrives here has already been
            told what Reasoner is, either by the home page or by a link
            straight into a §. The job of this block is to say what kind
            of document follows, and then get out of the way of §1. */}
        <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-48)]">
          <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div>
              <p className="mt-[var(--space-1)] font-sans text-[length:var(--text-2xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
                Capabilities
              </p>
            </div>
            <div className="min-w-0">
              <h1 className="max-w-[20ch] text-balance font-serif text-[length:var(--text-4xl)] font-normal leading-[var(--lh-display)] sm:text-[length:var(--text-6xl)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Eight mechanisms, and what holds each one.
              </h1>
              <p className="prose-measure mt-[var(--space-6)] text-[length:var(--text-2xl)] leading-[var(--lh-body)] text-[var(--text-2)]">
                Every section below is the same argument from a different angle: run the work past
                models that disagree, then keep the disagreement. Each says which part is a rule in
                code and which part is a brief given to a model, because the difference is the
                whole of what a claim like this is worth.
              </p>
              <Aside href="/how-it-works">Read a complete run instead &rarr;</Aside>
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
            VERIFIED is reserved for claims a non-model source can carry: a search result, a
            document you supplied, an executed check. This is a rule, not a prompt: no model is
            consulted when it runs, so no model can talk its way around it.
          </Body>

          <dl className="mt-[var(--space-10)] grid gap-[var(--space-6)] sm:grid-cols-2">
            <div className="border-t border-[var(--border)] pt-[var(--space-4)]">
              <dt className="epistemic-hypothesis pl-[var(--space-3)] font-sans text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
                Hypothesis
              </dt>
              <dd className="mt-[var(--space-3)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                The model asserted it and nothing else backs it. Plausible, reasoned, unconfirmed,
                and never dressed up as more.
              </dd>
            </div>
            <div className="border-t border-[var(--border)] pt-[var(--space-4)]">
              <dt className="epistemic-verified pl-[var(--space-3)] font-sans text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]">
                Verified
              </dt>
              <dd className="mt-[var(--space-3)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
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

        {/* ── §3 Image making ───────────────────────────────────
            Sits here because §2 has just established that which
            models see a request is decided by rule rather than by
            preference, and images are where that is easiest to
            watch working: the family a prompt lands in changes the
            models, the output format and the price.

            The exhibit lives on the home page. This section is the
            mechanism and that one is the evidence; collapsing them
            would leave either the four images unexplained or the
            explanation unproven. Every claim below maps to code —
            hypergate/sub_agents/image_model_selector.py (families,
            tier hint, no model names in the prompt),
            infrastructure/llm/image_model_catalogue.py (the
            ranking, one primary per lab, the vector exemption) and
            infrastructure/llm/image_generation.py (fallback
            hand-off, policy rewrite, retry). The family call is the
            only judgement here that a model makes. */}
        <Section id="image-making" marker="§3" name="Image making">
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
                <dt className="font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
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

          <Aside href="/#images">See four labs answer the same prompt →</Aside>
        </Section>

        {/* ── §4 Propagation ────────────────────────────────────── */}
        <Section id="propagation" marker="§4" name="Propagation">
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

        {/* ── §5 Sycophancy ─────────────────────────────────────────
            Last of the four Mechanism failures because it is the only one
            where the reader is the source of the distortion, and the page
            has spent five sections earning the standing to say so. Every
            Body paragraph below must correspond to a true
            SYCOPHANCY_CONTROLS entry — see MechanismDiagram's stage-03
            comment and tests/test_site_capabilities_sync.py. Do not add a
            paragraph here without adding its detector to
            scripts/update_mindmap_meta.py first. */}
        <Section id="sycophancy" marker="§5" name="Sycophancy">
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
              explicit audit of Phase 1&rsquo;s assumptions. A claim about another person&rsquo;s
              motives that
              only you supplied cannot be marked verified on your word alone; the destructive
              perspective is instructed to attack exactly those claims, not you.
            </Body>
          )}

          <Aside href="/how-it-works#adjudication">See the penalty on a real score matrix →</Aside>
        </Section>

        {/* ── §6 Voice ─────────────────────────────────
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
            here; see the PROSE_TELLS comment for why.

            Audited 2026-08-27, when this section carried three claims the
            code did not support. Two were fixed in code:
            HUMANIZATION_RULES reached only the synthesis, and now also
            ARTICLE_DRAFT_SYSTEM; the tell-quoting pass was dead
            (writing_humanize_prompt, zero call sites) and now runs as
            article phase 6a. Hence "the drafting prompt" below rather than
            the older, wrong "every phase of an article" — the developmental
            and copy edits are told NOT to change voice or word choice, so
            the rules cannot go there without contradicting them.

            The third claim was removed and must not return: author and
            publication voice matching. style_brief is populated by tests
            only, there is no API field for it, and §5 on this page says a
            tone control is not something we intend to sell. */}
        <Section id="voice" marker="§6" name="Voice">
          <Heading>A model cannot hear how it sounds.</Heading>
          <Lede>
            Machine prose has a fingerprint, and the model producing it is the last thing able to
            notice: significance inflation, vague attribution, the reflexive rule of three,{' '}
            <em>serves as</em> standing in for <em>is</em>. Reasoner does not ask for good writing.
            Every model that drafts prose you will read is handed the tells by name and told not
            to produce them.
          </Lede>
          <Body>
            The list is Wikipedia&rsquo;s, kept by the editors who clean this prose out of articles
            at volume and had to learn its signatures to do it. It arrives in four groups: the
            words, the openers, the structural tics, and the patterns that fake depth. The same
            block goes into the synthesis that closes a full run, into the instant answers, and
            into the prompt that drafts an article, so the standard is not a setting on one
            method. It goes in where the sentence is written, which is cheaper than finding the
            tell later and asking a second model to undo it.
          </Body>

          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-2">
            {PROSE_TELLS.map(({ tell, fix }) => (
              <div key={tell} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-mono text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-subtle)]">
                  <s className="decoration-[var(--border-strong)]">{tell}</s>
                </dt>
                <dd className="mt-[var(--space-1)] font-mono text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                  <span aria-hidden="true" className="text-[var(--text-subtle)]">&rarr;{' '}</span>
                  {fix}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            A brief is not a validator, and nothing checks the finished text against the list
            afterwards. What an article run adds is a phase whose only job is the tells that got
            through: an editor model quotes each one it can find in the draft, and only then is it
            allowed to rewrite the piece without them. Quoting first is the part that matters. A
            model asked to sound more human reaches for synonyms; one made to name the pattern has
            to deal with the sentence it just named.
          </Body>

          <Body>
            The editing passes on either side of it are not given the list, and that is deliberate.
            They are told not to change word choice, so a rule ordering them to substitute words
            would contradict the prompt it was attached to. A standard that is applied where it
            fits and withheld where it does not is worth more than one claimed everywhere.
          </Body>

          <Aside href="/#writing">See the run that pass belongs to &rarr;</Aside>
        </Section>

        {/* ── §7 Research ───────────────────────────────────────── */}
        <Section id="research" marker="§7" name="Research">
          <Heading>It searches like a researcher, not a search box.</Heading>
          <Lede>
            A single query returns what the query deserved. Reasoner runs an agentic loop that
            picks its own next move each iteration, goes broad before it goes narrow, and decides
            for itself when it has enough.
          </Lede>

          <ol
            role="list"
            className="mt-[var(--space-8)] grid list-none gap-[var(--space-4)] font-mono text-[length:var(--text-md)] leading-[var(--lh-body)]"
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
                <dt className="font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Aside href="/how-it-works#evidence">See what one run actually read →</Aside>
        </Section>

        {/* ── §8 Methods ────────────────────────────────────────── */}
        <Section id="methods" marker="§8" name="Methods">
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
                <dt className="font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {name}
                </dt>
                <dd className="mt-[var(--space-1)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
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
                  className="btn-lift flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
                >
                  Ask a question
                </Link>
                <Link
                  href="/how-it-works"
                  className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[length:var(--text-md)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
                >
                  Read a complete run
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
