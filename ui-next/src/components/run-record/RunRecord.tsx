import Link from 'next/link';
import type { ReactNode } from 'react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES, PROVIDERS } from '@/lib/capabilities.generated';
import { RUN, RUN_MODELS } from '@/lib/demo-record';
import { ApparatusToggle } from './ApparatusToggle';
import { RunIndex } from './RunIndex';
import { ScoreMatrix } from './ScoreMatrix';
import { Marks } from './Segments';

/**
 * This page is one real run of the product, laid out as the record that
 * run produced.
 *
 * The reasoning behind the form: Reasoner's output is not an answer, it is an
 * answer plus the argument, the scores, and the dissent. The home page states
 * that in prose; this page proves it with an artifact, and cannot be reused by
 * any product that has no such artifact. So the section names here are the
 * pipeline's own phase names, the figures are counted from `demo-record.ts`,
 * and the only two rounded shapes on the page are the things you can operate.
 *
 * A server component on purpose — the page is a document. The three client
 * islands are the two that need state (the apparatus toggle, the timing strip)
 * and the shared site header.
 */

const SOURCE_URLS = new Set(RUN.sources.map((source) => source.url));
const CITED_FROM_SWEEP = RUN.citations.filter((citation) => SOURCE_URLS.has(citation.url)).length;
const PERSPECTIVE_MODELS = RUN.phases.find((phase) => phase.id === 'positions')?.models ?? [];
const PRUNED = RUN.scores.filter((score) => !score.retained);

/** Facts with a document behind them in this repo — nothing aspirational. */
const TERMS: Array<{ term: string; detail: string }> = [
  {
    term: 'Source-available',
    detail:
      'Read the code under a Business Source License. It converts to Apache-2.0 in 2030.',
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

/* ── Section chrome ───────────────────────────────────────────────── */

/**
 * A section of the record: a marginal label that stays with you while you read
 * it, and the content column. The margin is the one structural irregularity on
 * the page and it earns its place — five phases deep into a record you should
 * never have to scroll up to find out which one you are in.
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

function Lede({ children }: { children: ReactNode }) {
  return (
    <p className="prose-measure font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
      {children}
    </p>
  );
}

/** Run metadata, set as a document header sets it: label, value, aligned. */
function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-[var(--space-1)] border-t border-[var(--border)] py-[var(--space-3)] sm:flex-row sm:gap-[var(--space-6)]">
      <dt className="w-[7rem] shrink-0 font-sans text-[length:var(--text-2xs)] uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
        {label}
      </dt>
      <dd className="min-w-0 font-mono text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-2)]">
        {children}
      </dd>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function RunRecord() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead ───────────────────────────────────────────
            Left-aligned and stated in nouns and verbs. The claim a
            centred display line would make here is instead made by the
            document that follows it. */}
        <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-32)]">
          <div className="grid gap-[var(--space-12)] lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-[var(--space-16)]">
            <div>
              <p className="font-sans text-[length:var(--text-xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--accent)]">
                How it works
              </p>

              <h1 className="mt-[var(--space-6)] max-w-[16ch] font-serif text-[length:var(--text-5xl)] font-normal leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                One run, with nothing left out.
              </h1>

              <p className="prose-measure mt-[var(--space-8)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                Reasoner puts a question through evidence search, four opposed positions written in
                parallel by models from competing labs, independent scoring, adversarial stress
                tests, and a synthesis whose claims are labelled VERIFIED, HYPOTHESIS, or UNKNOWN.
              </p>

              <p className="prose-measure mt-[var(--space-4)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                The rest of this page is one complete run of that pipeline — its sources, its
                scores, the two positions it threw away, and what it cost. It is a capture of the
                production code path, not a mockup.
              </p>

              <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-4)]">
                <Link
                  href="/chat"
                  className="btn-lift flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-base)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
                >
                  Run your own question
                </Link>
                <Link
                  href="/docs"
                  className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[length:var(--text-base)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
                >
                  Read the docs
                </Link>
              </div>
            </div>

            {/* The run's header block. Sets the register before a word of
                marketing copy has to: this is a record with a provenance. */}
            <dl className="h-fit border-b border-[var(--border)] lg:mt-[var(--space-2)]">
              <MetaRow label="Question">{RUN.question}</MetaRow>
              <MetaRow label="Preset">{RUN.preset}</MetaRow>
              <MetaRow label="Captured">{RUN.capturedOn}, production pipeline</MetaRow>
              <MetaRow label="Models">{RUN_MODELS.length} across competing labs</MetaRow>
              <MetaRow label="Wall clock">{RUN.ledger.seconds.toFixed(1)}s</MetaRow>
              <MetaRow label="Cost">
                ${RUN.ledger.costUsd.toFixed(4)} · {RUN.ledger.tokensTotal.toLocaleString('en-US')}{' '}
                tokens
              </MetaRow>
            </dl>
          </div>
        </header>

        <RunIndex />

        {/* ── Finding ────────────────────────────────────────────
            The record's result, presented before its working — the
            order a report is read in, not the order it was produced
            in. The toggle is the product's argument in one control. */}
        <Section id="synthesis" marker="§5" name="Synthesis">
          <h2 className="font-serif text-[length:var(--text-3xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            The finding, and what stands behind it.
          </h2>
          <div className="mt-[var(--space-6)]">
            <Lede>
              This is what the run returned. Presented first, ahead of its own working — the way a
              report is read rather than the way it is produced. Take the record away and the words
              are unchanged; what you lose is every means of checking them.
            </Lede>
          </div>
          <div className="mt-[var(--space-10)]">
            <ApparatusToggle />
          </div>
        </Section>

        {/* ── §1 Evidence ───────────────────────────────────────── */}
        <Section id="evidence" marker="§1" name="Evidence Search">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            What the run read first.
          </h2>
          <div className="mt-[var(--space-4)]">
            <Lede>
              The sweep returned {RUN.sources.length} sources in{' '}
              {RUN.phases[0].seconds.toFixed(1)}s — every one of them read before a single position
              was written. {CITED_FROM_SWEEP} of the {RUN.citations.length} URLs the synthesis ends
              up citing came back from this list, and each is linked from the finding above.
            </Lede>
          </div>

          <ol role="list" className="mt-[var(--space-8)] list-none">
            {RUN.sources.map((source) => (
              <li
                key={source.url}
                className="flex gap-[var(--space-4)] border-t border-[var(--border)] py-[var(--space-4)] last:border-b"
              >
                <span className="nums-tabular w-[2ch] shrink-0 font-mono text-[length:var(--text-xs)] text-[var(--text-subtle)]">
                  {source.index}
                </span>
                <span className="min-w-0">
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="link-smooth block font-serif text-[length:var(--text-base)] leading-[var(--lh-subhead)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--accent)]"
                  >
                    {source.title}
                  </a>
                  <span className="mt-[var(--space-1)] block truncate font-mono text-[length:var(--text-2xs)] text-[var(--text-subtle)]">
                    {source.domain}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </Section>

        {/* ── §2 Positions ──────────────────────────────────────── */}
        <Section id="positions" marker="§2" name="Perspectives">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            Four positions, written against each other.
          </h2>
          <div className="mt-[var(--space-4)]">
            <Lede>
              Constructive builds the case, destructive attacks it, systemic follows the
              second-order effects, minimalist argues for doing less. They run in parallel on models
              from different labs, so none of them can quietly agree with the others. Not one of
              them is the answer — all four go to the critic.
            </Lede>
          </div>

          <p className="mt-[var(--space-6)] font-mono text-[length:var(--text-2xs)] leading-[var(--lh-body)] text-[var(--text-subtle)]">
            Generated by {PERSPECTIVE_MODELS.join(' · ')}
          </p>

          <div className="mt-[var(--space-8)] grid gap-x-[var(--space-10)] gap-y-[var(--space-8)] md:grid-cols-2">
            {RUN.positions.map((position) => (
              <article key={position.id} className="border-t border-[var(--border)] pt-[var(--space-4)]">
                <h3 className="font-sans text-[length:var(--text-xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text)]">
                  {position.id}
                </h3>
                <p className="mt-[var(--space-3)] font-serif text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  <Marks segments={position.excerpt} />
                </p>
                {position.insights[0] && (
                  <p className="mt-[var(--space-4)] border-l-2 border-[var(--accent-dim)] pl-[var(--space-3)] font-sans text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-2)]">
                    {position.insights[0]}
                  </p>
                )}
              </article>
            ))}
          </div>
        </Section>

        {/* ── §3 Adjudication ───────────────────────────────────── */}
        <Section id="adjudication" marker="§3" name="Critique &amp; Pruning">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            Scored by a model with no stake in the answer.
          </h2>
          <div className="mt-[var(--space-4)]">
            <Lede>
              {PRUNED.length} of the {RUN.scores.length} positions were pruned here — including one
              that had reached the same conclusion the run eventually publishes, and was cut anyway
              for stating it further than its evidence went. Agreeing with the outcome is not what
              gets a position kept.
            </Lede>
          </div>

          <div className="mt-[var(--space-10)]">
            <ScoreMatrix />
          </div>
        </Section>

        {/* ── §4 Stress ─────────────────────────────────────────── */}
        <Section id="stress" marker="§4" name="Stress Testing">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            Then it is attacked.
          </h2>
          <div className="mt-[var(--space-4)]">
            <Lede>
              What survived critique gets run against adversarial scenarios. The phase reports a
              survival rate and, where it has one, the failure mode it found. Both tests from this
              run are below, printed as they came back.
            </Lede>
          </div>

          <div className="mt-[var(--space-8)]">
            {RUN.stress.map((test, i) => (
              <div key={i} className="border-t border-[var(--border)] py-[var(--space-6)] last:border-b">
                <div className="flex items-baseline gap-[var(--space-4)]">
                  <span className="nums-tabular font-mono text-[length:var(--text-2xl)] leading-[var(--lh-tight)] text-[var(--text)]">
                    {Math.round(test.survivalRate * 100)}%
                  </span>
                  <span className="font-sans text-[length:var(--text-2xs)] uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                    survival · {test.scenario}
                  </span>
                </div>

                <span
                  aria-hidden="true"
                  className="mt-[var(--space-3)] block h-[3px] w-full max-w-[var(--measure-tight)] bg-[var(--border)]"
                >
                  <span
                    className="block h-full bg-[var(--accent)]"
                    style={{ width: `${test.survivalRate * 100}%` }}
                  />
                </span>

                <p className="prose-measure mt-[var(--space-4)] font-serif text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {test.failureMode || (
                    <span className="text-[var(--text-subtle)]">
                      This test returned a rate with no accompanying prose. Shown as it came back
                      rather than filled in.
                    </span>
                  )}
                </p>
              </div>
            ))}
          </div>
        </Section>

        {/* ── Ledger ────────────────────────────────────────────── */}
        <Section marker="§0" name="Ledger">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            What the record cost.
          </h2>
          <div className="mt-[var(--space-4)]">
            <Lede>
              Every run reports its own consumption. This one — five phases, {RUN_MODELS.length}{' '}
              models, {RUN.sources.length} sources, {RUN.scores.length} scored positions — came to
              less than a third of a cent.
            </Lede>
          </div>

          <dl className="nums-tabular mt-[var(--space-8)] grid gap-[var(--space-6)] sm:grid-cols-2 lg:grid-cols-4">
            {[
              { term: 'Wall clock', value: `${RUN.ledger.seconds.toFixed(1)}s` },
              /* Locale pinned: a bare toLocaleString() follows the SERVER's
                 locale, which turned 10,297 into "10.297" on a Greek host. */
              { term: 'Tokens in', value: RUN.ledger.tokensIn.toLocaleString('en-US') },
              { term: 'Tokens out', value: RUN.ledger.tokensOut.toLocaleString('en-US') },
              { term: 'Cost', value: `$${RUN.ledger.costUsd.toFixed(4)}` },
            ].map(({ term, value }) => (
              <div key={term} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-sans text-[length:var(--text-2xs)] uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                  {term}
                </dt>
                <dd className="mt-[var(--space-2)] font-mono text-[length:var(--text-xl)] leading-[var(--lh-tight)] text-[var(--text)]">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* ── Interface ─────────────────────────────────────────── */}
        <Section marker="API" name="Interface">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            The record comes back as JSON.
          </h2>
          <div className="mt-[var(--space-4)]">
            <Lede>
              Everything on this page — sources, positions, per-axis scores, bias flags, survival
              rates, the token ledger — is a field in the run response. A typed SDK, a documented
              HTTP API, and an MCP server so an agent can call Reasoner as a tool. Scoped, revocable
              keys; no dashboard click-through to get a first response.
            </Lede>
          </div>

          <pre className="mt-[var(--space-8)] overflow-x-auto border border-[var(--border)] bg-[var(--surface)] p-[var(--space-6)] font-mono text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-2)]">
            <code>{`curl https://reasoner.app/api/agent/run/sync \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "${RUN.question}",
       "preset": "${RUN.preset}"}'

# → { "synthesis": …, "scores": [ … ], "stress_tests": [ … ],
#     "sources": [ … ], "total_cost_usd": ${RUN.ledger.costUsd.toFixed(4)} }`}</code>
          </pre>

          {/* A plain list, not a <dl>: the figure and its label are one phrase
              here ("31 reasoning methods"), and a description list would need a
              <dt> that repeats the visible label to a screen reader. */}
          <ul
            role="list"
            className="nums-tabular mt-[var(--space-8)] flex list-none flex-wrap gap-x-[var(--space-8)] gap-y-[var(--space-4)]"
          >
            {[
              { term: 'reasoning methods', value: CAPABILITIES.methods },
              { term: 'tuned presets', value: CAPABILITIES.presets },
              { term: 'routable models', value: `${CAPABILITIES.routableModels}+` },
              { term: 'direct provider adapters', value: CAPABILITIES.providerAdapters },
            ].map(({ term, value }) => (
              <li key={term} className="flex items-baseline gap-[var(--space-2)]">
                <span className="font-mono text-[length:var(--text-lg)] leading-[var(--lh-tight)] text-[var(--text)]">
                  {value}
                </span>
                <span className="font-sans text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
                  {term}
                </span>
              </li>
            ))}
          </ul>

          <p className="mt-[var(--space-6)] font-sans text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-subtle)]">
            Direct adapters: {PROVIDERS.join(', ')}. Everything else routes through OpenRouter.{' '}
            <Link
              href="/developers"
              className="link-smooth underline underline-offset-4 hover:text-[var(--text-2)]"
            >
              The developer surface
            </Link>
            .
          </p>
        </Section>

        {/* ── Terms ─────────────────────────────────────────────── */}
        <Section marker="—" name="Terms">
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
            Where your data sits.
          </h2>

          <dl className="mt-[var(--space-8)]">
            {TERMS.map(({ term, detail }) => (
              <div
                key={term}
                className="flex flex-col gap-[var(--space-1)] border-t border-[var(--border)] py-[var(--space-4)] last:border-b sm:flex-row sm:gap-[var(--space-8)]"
              >
                <dt className="w-[14rem] shrink-0 font-sans text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
                  {term}
                </dt>
                <dd className="prose-measure font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>

          <p className="mt-[var(--space-6)] font-sans text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-subtle)]">
            <Link href="/security" className="link-smooth underline underline-offset-4 hover:text-[var(--text-2)]">
              Security detail
            </Link>{' '}
            ·{' '}
            <Link href="/privacy" className="link-smooth underline underline-offset-4 hover:text-[var(--text-2)]">
              Privacy
            </Link>{' '}
            ·{' '}
            <Link href="/subprocessors" className="link-smooth underline underline-offset-4 hover:text-[var(--text-2)]">
              Sub-processors
            </Link>
          </p>
        </Section>

        {/* ── Close ─────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] py-[var(--section-y)]">
          <div className="grid gap-[var(--space-8)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div />
            <div>
              <h2 className="prose-measure font-serif text-[length:var(--text-3xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
                Your question gets the same treatment.
              </h2>
              <p className="prose-measure mt-[var(--space-4)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                Same phases, same scoring, same record at the end — and a decision you can hand to
                someone else with the working attached.
              </p>
              <Link
                href="/chat"
                className="btn-lift mt-[var(--space-10)] inline-flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-base)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
              >
                Run your own question
              </Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
