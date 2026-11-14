import Link from 'next/link';
import type { ReactNode } from 'react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, SYCOPHANCY_CONTROLS } from '@/lib/capabilities.generated';
import { EPISTEMIC_TAG, epistemicClassName } from '@/lib/remark-epistemic';

/**
 * /capabilities in the site world "The product performs" (spec/art-direction.md):
 * the mechanism argument, in eight parts.
 *
 * Every section is the same claim from a different angle: Reasoner runs work
 * past models that disagree, then makes the disagreement part of the output.
 * Ordering is by strength of evidence, not by glamour. Epistemic labelling
 * leads because it is the only deterministic guarantee here: a rule in code,
 * with no model in the loop. The proof for all of it is /how-it-works, a
 * captured production run. The hero fragment says, for each section, what
 * holds it: a rule in code, a test, or a brief given to a model.
 *
 * Anchors are what inbound links are written against (several moved here from
 * the home page). Never rename an id.
 *
 * Copy discipline: every figure comes from `capabilities.generated.ts`, which
 * is regenerated from the live registry on each commit. Nothing here claims
 * enforcement the code does not perform. See
 * docs/plans/landing-capability-pivot.md §3 for the claim-to-code table.
 */

/* ── Content ──────────────────────────────────────────────────────── */

/** What holds each section's claim. Read from the copy below; keep in step with it. */
const MECHANISMS = [
  { id: 'hallucination', name: 'Epistemic labelling', held: 'A rule in code' },
  { id: 'bias', name: 'Cross-bloc routing', held: 'A validator and a test' },
  { id: 'image-making', name: 'Image routing', held: 'Code, after one model reading' },
  { id: 'propagation', name: 'Propagation resistance', held: 'Prompts, held by tests' },
  { id: 'sycophancy', name: 'Sycophancy controls', held: 'Code and prompts' },
  { id: 'voice', name: 'Prose standards', held: 'A brief to the model' },
  { id: 'research', name: 'Agentic research', held: 'A model choosing each step' },
  { id: 'methods', name: 'Reasoning methods', held: 'A pipeline per method' },
];

/** How a claim's label is decided (the downgrade rule in the synthesis path). */
const LABEL_RULE = [
  { backing: 'Only the model that wrote it', label: 'HYPOTHESIS' },
  { backing: 'A search result', label: 'VERIFIED' },
  { backing: 'A document you supplied', label: 'VERIFIED' },
  { backing: 'An executed check', label: 'VERIFIED' },
] as const;

/**
 * The four search actions the research loop can choose between at each
 * iteration (phases/_prism.py), plus uploaded documents. "done" is omitted:
 * it is a terminator, not a capability.
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
  { name: 'Vector', desc: 'Logos, icons, flat marks, routed to a model that emits real SVG.' },
  { name: 'Photoreal', desc: 'People, products, scenes. Anything that has to survive close looking.' },
  { name: 'Text in image', desc: 'Posters, signage, labels: only the models that can spell.' },
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
 * rules, two filler cuts, and the specificity standard, chosen because each
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

/* ── Chrome ───────────────────────────────────────────────────────── */

const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';
const FIGURE = 'w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] text-[var(--site-ink)]';
const ROW = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] last:border-b-0';

/**
 * One mechanism. With a figure: text and fragment side by side (the fragment
 * leads on the light field). Without: the heading on the left, the argument on
 * the right. The heading is two lines, the house rule for every headline.
 */
function Section({
  id,
  lines,
  field = false,
  figure,
  children,
}: {
  id: string;
  lines: [string, string];
  field?: boolean;
  figure?: ReactNode;
  children: ReactNode;
}) {
  const heading = (
    <h2 id={`${id}-h`} className={HEAD}>
      <span className="block">{lines[0]}</span>
      <span className="block">{lines[1]}</span>
    </h2>
  );
  return (
    <section
      id={id}
      aria-labelledby={`${id}-h`}
      className={`scroll-mt-[var(--space-20)] ${field ? 'bg-[var(--site-field)] text-[var(--site-field-ink)]' : ''}`}
    >
      <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-10)] px-[var(--site-margin)] py-[var(--space-16)] lg:grid-cols-12 lg:items-center lg:gap-[var(--space-12)] lg:py-[var(--space-24)]">
        {figure ? (
          <>
            <div className={field ? 'lg:col-span-5 lg:col-start-8 lg:row-start-1' : 'lg:col-span-5'}>
              {heading}
              {children}
            </div>
            <div
              data-reveal
              className={`flex min-w-0 ${field ? 'lg:col-span-6 lg:col-start-1 lg:row-start-1' : 'lg:col-span-6 lg:col-start-7'}`}
            >
              {figure}
            </div>
          </>
        ) : (
          <>
            <div className="self-start lg:col-span-5">{heading}</div>
            <div className="lg:col-span-6 lg:col-start-7 [&>*:first-child]:mt-0">{children}</div>
          </>
        )}
      </div>
    </section>
  );
}

function Body({ children }: { children: ReactNode }) {
  return <p className={`mt-[var(--space-6)] max-w-[60ch] ${BODY}`}>{children}</p>;
}

/** The proof link at the foot of a section. */
function More({ href, children }: { href: string; children: ReactNode }) {
  return (
    <p className={`mt-[var(--space-8)] ${BODY}`}>
      {/* text-current: .site-link pins the dark-ground ink, unreadable on the light field. */}
      <Link href={href} className="site-link text-current">
        {children}
      </Link>
    </p>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function CapabilitiesPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), what holds each mechanism (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>What holds</span>
              </span>
              <span className="site-line">
                <span>each claim.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Eight mechanisms, one argument: run the work past models that disagree, then keep the
                disagreement. Each says whether a rule in code holds it, or a brief to a model.
              </p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>
                The difference is the whole of what a claim like this is worth.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/chat" className="site-button">
                  Ask a question
                </Link>
                <Link href="/how-it-works" className={`site-link ${BODY}`}>
                  Read a complete run
                </Link>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>What holds each one</figcaption>
              <ol className="list-none">
                {MECHANISMS.map(({ id, name, held }) => (
                  <li key={id} className="border-b border-[var(--site-line)]">
                    <a
                      href={`#${id}`}
                      className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-[var(--space-3)] px-[var(--space-4)] py-[var(--space-3)] hover:bg-[var(--site-surface)]"
                    >
                      <span className="font-semibold">{name}</span>
                      <span className="text-right text-[var(--site-muted)]">{held}</span>
                    </a>
                  </li>
                ))}
              </ol>
              <p className="px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
                A rule in code runs with no model in the loop. A brief is an instruction a model can
                still miss.
              </p>
            </figure>
          </div>
        </header>

        {/* ── Epistemic labelling: leads because it is the only
            deterministic guarantee on the page. ── */}
        <Section
          id="hallucination"
          lines={['A model cannot', 'vouch for itself.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>How a claim gets its label</figcaption>
              <ul className="list-none">
                {LABEL_RULE.map(({ backing, label }) => (
                  <li key={backing} className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-[var(--space-3)] ${ROW}`}>
                    <span>{backing}</span>
                    <span className={epistemicClassName(EPISTEMIC_TAG[label])}>{label}</span>
                  </li>
                ))}
              </ul>
              <p className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
                Applied in code before the answer reaches you. No model is consulted.
              </p>
            </figure>
          }
        >
          <Body>
            Most products ask a model whether it is confident and print the answer. Reasoner does not
            accept it. If a claim&rsquo;s only backing is the model that produced it, the label is
            downgraded from verified to hypothesis in code, before it reaches you.
          </Body>
          <Body>
            Verified is reserved for claims a non-model source can carry: a search result, a document
            you supplied, an executed check. This is a rule, not a prompt: no model is consulted when it
            runs, so no model can talk its way around it.
          </Body>
          <More href="/how-it-works#synthesis">See the labels on a real answer</More>
        </Section>

        {/* ── Cross-bloc routing ── */}
        <Section id="bias" lines={['Scored from', 'a different bloc.']} field>
          <Body>
            Cross-lab is not enough. Two labs in the same country share an ideological prior, so
            routing a question past both proves less than it appears to. Reasoner routes so the model
            writing the final answer and the model pruning it never come from the same geopolitical
            bloc, and so the generators span at least two.
          </Body>
          <Body>
            The constraint is grounded in published work: Buyl et al., <em>npj AI</em> 2026, which
            finds the creator&rsquo;s bloc to be the dominant axis of a model&rsquo;s ideological bias.
            It is held by a validator and a test rather than by good intentions, so a preset that
            violates it fails the build.
          </Body>
          <Body>
            Separately, a dedicated critic tags each candidate answer with typed bias flags and
            subtracts a severity-weighted penalty from its score. Flagged candidates lose on the
            arithmetic, and you can see which flags they drew.
          </Body>
          <More href="/how-it-works#adjudication">See the scores and their bias flags</More>
        </Section>

        {/* ── Image routing ──────────────────────────────────────
            Follows cross-bloc routing because that section establishes that
            which models see a request is decided by rule rather than
            preference, and images are where that is easiest to watch. The
            exhibit lives on the home page (#images); this is the mechanism.
            Every claim maps to code: hypergate/sub_agents/image_model_selector.py
            (families, tier hint, no model names in the prompt),
            infrastructure/llm/image_model_catalogue.py (the ranking, one
            primary per lab, the vector exemption) and
            infrastructure/llm/image_generation.py (fallback hand-off, policy
            rewrite, retry). The family call is the only judgement here a model
            makes. */}
        <Section
          id="image-making"
          lines={['No house model,', 'no favourite lab.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>The families a prompt is read into</figcaption>
              <dl>
                {IMAGE_FAMILIES.map(({ name, desc }) => (
                  <div key={name} className={ROW}>
                    <dt className="font-semibold">{name}</dt>
                    <dd className="text-[var(--site-muted)]">{desc}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            An image prompt is read for what it asks for (a logo, a photograph, a poster, an edit of
            something you supplied) and that reading picks the models. The classifier never sees a
            model name, only the capability the picture needs, so nothing is routed to a favourite on
            reputation.
          </Body>
          <Body>
            Which model then serves that family is decided in code. Each candidate ranks itself from
            its own identifier, the size word and version number its lab published it under, so a new
            one takes its place with no edit here. Price comes from the live catalogue: on the budget
            tier it leads, on premium it only breaks ties. Primaries are taken one per lab. Vector is
            the one exception: a single lab ships SVG generators, so you get fewer images rather than a
            raster answering to the name of a vector.
          </Body>
          <Body>
            A refusal is routing, not an error. A primary that fails hands off to the fallback behind
            it, and a content-policy block sends the prompt back to be rewritten, with the whole
            selection tried again before anything is returned as a failure.
          </Body>
          <More href="/#images">See four labs answer the same prompt</More>
        </Section>

        {/* ── Propagation resistance ── */}
        <Section id="propagation" lines={['An idea cannot', 'spread itself here.']} field>
          <Body>
            Systems that pass work between models have a failure mode a single model does not. Text
            that persuades one stage to carry it into the next can ride the whole pipeline and settle
            into what the system remembers. Reasoner is built so it has nowhere to travel.
          </Body>
          <Body>
            Every stage that reads outside text (a web page, an earlier model, a recalled memory, an
            API caller) is told in its system prompt that such text is data and never instruction, and
            that anything asking to be repeated, preserved, or passed onward is a finding to report
            rather than an order to obey. The four generators never read each other, so nothing moves
            sideways between them. Recalled memory enters as a user message, never as an instruction,
            carrying the run and model it came from.
          </Body>
          <Body>
            The design follows Papadopoulos et al., <em>Mind Viruses: Self-Propagating Ideas in
            Multi-Agent LLM Systems</em> (2026), which measures each of these controls independently.
            The system-prompt warning is the one that held against fifteen generations of adversarial
            payloads; keeping memory out of the instruction channel is the difference the paper
            measures between most propagation succeeding and almost none of it. Both are held by
            tests, so a change that reopens either fails the build.
          </Body>
        </Section>

        {/* ── Sycophancy ─────────────────────────────────────────
            The only section where the reader is the source of the
            distortion. Every Body paragraph below must correspond to a true
            SYCOPHANCY_CONTROLS entry and sit behind its guard: see
            MechanismDiagram's stage-03 comment and
            tests/test_site_capabilities_sync.py, which parses this section.
            Do not add a paragraph here without adding its detector to
            scripts/update_mindmap_meta.py first. */}
        <Section id="sycophancy" lines={['Not built to', 'be agreed with.']}>
          <p className={`mt-[var(--space-6)] max-w-[60ch] ${BODY}`}>
            Assistants trained on human approval learn that agreement scores well. Across five
            preregistered studies, Ibrahim et al. found sycophantic AI gave no better advice than a
            neutral system. The entire gain was in how understood people felt, and three weeks of it
            left them measurably less satisfied with the people in their lives.
          </p>
          {SYCOPHANCY_CONTROLS.noApprovalGradient && SYCOPHANCY_CONTROLS.confidencePenalty && (
            <Body>
              Reasoner has no approval gradient to climb. The signal that decides which models get
              used is built from completion, schema validity, critique score and stress-test survival;
              a rating you give is recorded for you and never reaches it. Every run also carries a
              generator whose only instruction is to find flaws, and the critic subtracts a penalty
              from any answer that states unsupported claims confidently. In the arithmetic, honest
              uncertainty outscores false confidence.
            </Body>
          )}
          {SYCOPHANCY_CONTROLS.noStyleSelector && (
            <Body>
              There is no warmth slider and no personality picker. Offered three unlabelled styles in
              that study, a majority chose the flattering one, and not for its advice. They chose it
              because it was easiest to talk to. Choosing a tone is not a control we intend to sell
              you.
            </Body>
          )}
          {SYCOPHANCY_CONTROLS.directPathEpistemicRules && SYCOPHANCY_CONTROLS.premiseAudit && (
            <Body>
              A stated conclusion is treated as a claim to evaluate, not a premise to build on: on the
              direct-answer path by system prompt, and inside the full pipeline by an explicit audit of
              Phase 1&rsquo;s assumptions. A claim about another person&rsquo;s motives that only you
              supplied cannot be marked verified on your word alone; the destructive perspective is
              instructed to attack exactly those claims, not you.
            </Body>
          )}
          <More href="/how-it-works#adjudication">See the penalty on real scores</More>
        </Section>

        {/* ── Prose standards ────────────────────────────────────
            Copy discipline: the humanization block is a brief given to the
            models, NOT a validator; nothing diffs the finished text against
            it. The third paragraph says so and must keep saying so. The only
            enforcement claimed is the article pipeline's style pass (role
            article_humanize, phase 6a), a real phase with a real model.
            "The drafting prompt" is deliberate: the developmental and copy
            edits are told NOT to change word choice, so the rules cannot go
            there. Author and publication voice matching was removed on
            2026-08-27 and must not return: style_brief is populated by tests
            only and has no API field. */}
        <Section
          id="voice"
          lines={['A model cannot', 'hear how it sounds.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Named in the brief, and what replaces them</figcaption>
              <dl>
                {PROSE_TELLS.map(({ tell, fix }) => (
                  <div key={tell} className={`grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <dt className="text-[var(--site-muted)]">
                      <s>
                        <code>{tell}</code>
                      </s>
                    </dt>
                    <dd>
                      <code>{fix}</code>
                    </dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            Machine prose has a fingerprint, and the model producing it is the last thing able to
            notice: significance inflation, vague attribution, the reflexive rule of three,{' '}
            <em>serves as</em> standing in for <em>is</em>. Every model that drafts prose you will read
            is handed the tells by name and told not to produce them. The list is Wikipedia&rsquo;s,
            kept by the editors who clean this prose out of articles at volume.
          </Body>
          <Body>
            The same block goes into the synthesis that closes a full run, the instant answers, and
            the prompt that drafts an article. A brief is not a validator, and nothing checks the
            finished text against the list afterwards. What an article run adds is a phase whose only
            job is the tells that got through: an editor model quotes each one it finds, and only then
            rewrites the piece without them.
          </Body>
          <More href="/#writing">See the run that pass belongs to</More>
        </Section>

        {/* ── Agentic research ── */}
        <Section
          id="research"
          lines={['It searches like', 'a researcher.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>One loop, broad before narrow</figcaption>
              <ol className="list-none">
                {QUERY_PROGRESSION.map((query, i) => (
                  <li key={query} className={`flex items-baseline gap-[var(--space-3)] ${ROW}`}>
                    <span className="shrink-0 text-[var(--site-muted)]">Step {i + 1}</span>
                    <code>{query}</code>
                  </li>
                ))}
              </ol>
              <p className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold">
                Five kinds of retrieval to choose from
              </p>
              <dl>
                {RESEARCH_ACTIONS.map(({ name, desc }) => (
                  <div key={name} className={`border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]`}>
                    <dt className="font-semibold">{name}</dt>
                    <dd className="text-[var(--site-muted)]">{desc}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            A single query returns what the query deserved. Reasoner runs an agentic loop that picks
            its own next move each iteration, goes broad before it goes narrow, and decides for itself
            when it has enough.
          </Body>
          <Body>
            At each step it chooses among five kinds of retrieval, then reads what it finds rather than
            skimming a snippet. At the deepest tier it plans five or more iterations and
            cross-references before it will stop.
          </Body>
          <More href="/how-it-works#evidence">See what one run read</More>
        </Section>

        {/* ── Reasoning methods ── */}
        <Section
          id="methods"
          lines={[`${CAPABILITIES.methods} methods.`, `Not ${CAPABILITIES.methods} prompts.`]}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Methods with a pipeline of their own</figcaption>
              <dl className="grid sm:grid-cols-2">
                {METHODS.map(({ name, desc }) => (
                  <div key={name} className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
                    <dt className="font-semibold">{name}</dt>
                    <dd className="text-[var(--site-muted)]">{desc}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            Named reasoning techniques are usually sold as instructions bolted onto one chat
            completion. Here each is a separate pipeline with its own phases, its own model routing,
            and its own failure modes. Tree-of-Thoughts backtracks. Program-of-Thoughts executes the
            code it writes.
          </Body>
          <Body>
            Each ships in a budget and a premium tier, for {CAPABILITIES.presets} routing
            configurations in total, spanning {CAPABILITIES.routableModels.toLocaleString('en-US')}{' '}
            routable models. You can pick one, or let the router pick from the question.
          </Body>
          <More href="/docs">Read the method reference</More>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Ask what you</span>
            <span className="block">would check by hand.</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            The kind of question where being confidently wrong would cost you. That is the case this
            was built for.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/chat" className="site-button">
              Ask a question
            </Link>
            <Link href="/how-it-works" className={`site-link ${BODY}`}>
              Read a complete run
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
