import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES } from '@/lib/capabilities.generated';
import { RUN, RUN_MODELS, SCORE_AXES } from '@/lib/demo-record';
import { ApparatusToggle } from './ApparatusToggle';
import { RunIndex } from './RunIndex';
import { Marks } from './Segments';

/**
 * /how-it-works in the site world "The product performs" (spec/art-direction.md).
 *
 * One real run of the product, walked phase by phase. Each section shows that
 * phase's actual output as an interface fragment: the sources it read, the
 * four positions, the critic's scores, the stress tests, the labelled answer,
 * and the JSON it comes back as. Every figure is counted from
 * lib/demo-record.ts, a capture of the production pipeline.
 *
 * A server component on purpose: the page is a document. The client islands
 * are the timing chart and the record toggle.
 */

const CITED_URLS = new Set(RUN.citations.map((citation) => citation.url));
const CITED_FROM_SWEEP = RUN.sources.filter((source) => CITED_URLS.has(source.url)).length;
const PERSPECTIVE_MODELS = RUN.phases.find((phase) => phase.id === 'positions')?.models ?? [];
const PRUNED = RUN.scores.filter((score) => !score.retained);

const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';
const FIGURE = 'w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)]';
const SECTION = 'mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center';

/** A section heading set as two lines, the house rule for every headline. */
function Heading({ id, lines }: { id: string; lines: [string, string] }) {
  return (
    <h2 id={id} className={HEAD}>
      <span className="block">{lines[0]}</span>
      <span className="block">{lines[1]}</span>
    </h2>
  );
}

export default function RunRecord() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), the run's header and timing (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>One run,</span>
              </span>
              <span className="site-line">
                <span>start to finish.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                A real question through every phase: evidence, four opposed positions, a critic,
                stress tests and an answer with each claim labelled.
              </p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>
                Captured on {RUN.capturedOn} from the production pipeline. Nothing below is a mockup,
                and nothing the run threw away is hidden.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/chat" className="site-button">
                  Run your own question
                </Link>
                <a href="#synthesis" className={`site-link ${BODY}`}>
                  Skip to the answer
                </a>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <RunIndex />
          </div>
        </header>

        {/* ── Evidence ── */}
        <section id="evidence" aria-labelledby="evidence-h" className={`${SECTION} scroll-mt-[var(--space-20)]`}>
          <div className="lg:col-span-5">
            <Heading id="evidence-h" lines={['It reads', 'before it writes.']} />
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              The search returned {RUN.sources.length} sources in {RUN.phases[0].seconds.toFixed(1)}s,
              all read before a single position was written. {CITED_FROM_SWEEP} of them are cited in
              the final answer, each linked from the claim it supports.
            </p>
          </div>
          <figure data-ui data-reveal className={`${FIGURE} bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7`}>
            <figcaption className={CAP}>Sources, in the order they came back</figcaption>
            <ol className="list-none">
              {RUN.sources.map((source) => (
                <li
                  key={source.url}
                  className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] last:border-b-0"
                >
                  <span className="text-[var(--site-muted)] nums-tabular">{source.index}</span>
                  <span className="min-w-0">
                    <a href={source.url} target="_blank" rel="noopener noreferrer" className="site-link">
                      {source.title}
                    </a>
                    <span className="block truncate text-[var(--site-muted)]">{source.domain}</span>
                  </span>
                  <span className={CITED_URLS.has(source.url) ? 'font-semibold text-[var(--site-accent)]' : 'text-[var(--site-muted)]'}>
                    {CITED_URLS.has(source.url) ? 'Cited' : 'Read'}
                  </span>
                </li>
              ))}
            </ol>
          </figure>
        </section>

        {/* ── Positions: light field ── */}
        <section id="positions" aria-labelledby="positions-h" className="scroll-mt-[var(--space-20)] bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className={SECTION}>
            <figure
              data-ui
              data-reveal
              className={`${FIGURE} order-last bg-[var(--site-bg)] text-[var(--site-ink)] lg:order-none lg:col-span-6`}
            >
              <figcaption className={CAP}>Four positions, written in parallel</figcaption>
              <ul className="list-none">
                {RUN.positions.map((position) => (
                  <li key={position.id} className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-4)] last:border-b-0">
                    <p className="font-semibold capitalize">{position.id}</p>
                    {position.insights[0] && <p className="mt-[var(--space-1)]">{position.insights[0]}</p>}
                    <p className="mt-[var(--space-2)] text-[var(--site-muted)]">
                      <Marks segments={position.excerpt} />
                    </p>
                  </li>
                ))}
              </ul>
            </figure>
            <div className="lg:col-span-5 lg:col-start-8">
              <Heading id="positions-h" lines={['Four positions,', 'blind to each other.']} />
              <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
                Constructive builds the case, destructive attacks it, systemic follows the
                second-order effects, minimalist argues for doing less. They run at the same time on
                models from different labs ({PERSPECTIVE_MODELS.join(', ')}), and none sees the
                others, so none can quietly agree. All four go to the critic.
              </p>
            </div>
          </div>
        </section>

        {/* ── Critique ── */}
        <section id="adjudication" aria-labelledby="adjudication-h" className={`${SECTION} scroll-mt-[var(--space-20)]`}>
          <div className="lg:col-span-5">
            <Heading id="adjudication-h" lines={['A critic', 'scores them.']} />
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              A model from a different lab scores each position on four axes, then applies penalties.
              {' '}{PRUNED.length} of the {RUN.scores.length} were pruned, including one that reached the
              conclusion the run ends up publishing: it stated it further than its evidence went.
              Agreeing with the outcome is not what keeps a position.
            </p>
          </div>
          <figure data-ui data-reveal className={`${FIGURE} bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7`}>
            <figcaption className={CAP}>Scores out of 10, after penalties</figcaption>
            <ul className="list-none">
              {RUN.scores.map((score) => (
                <li key={score.position} className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-4)] last:border-b-0">
                  <div className="flex items-baseline justify-between gap-[var(--space-3)]">
                    <span className="font-semibold capitalize">{score.position}</span>
                    <span className="flex items-baseline gap-[var(--space-3)] nums-tabular">
                      <span className={score.retained ? 'font-semibold text-[var(--site-accent)]' : 'text-[var(--site-muted)]'}>
                        {score.retained ? 'Kept' : 'Pruned'}
                      </span>
                      <span className="font-display text-[length:var(--site-lead)]">{score.total.toFixed(1)}</span>
                    </span>
                  </div>
                  <p className="mt-[var(--space-1)] text-[var(--site-muted)] nums-tabular">
                    {SCORE_AXES.map(({ key, label }) => `${label} ${score[key]}`).join(' · ')}
                  </p>
                  {score.biasFlags.length > 0 && <p className="mt-[var(--space-1)]">Bias flag: {score.biasFlags.join('; ')}</p>}
                </li>
              ))}
            </ul>
          </figure>
        </section>

        {/* ── Stress: light field ── */}
        <section id="stress" aria-labelledby="stress-h" className="scroll-mt-[var(--space-20)] bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className={SECTION}>
            <figure
              data-ui
              data-reveal
              className={`${FIGURE} order-last bg-[var(--site-bg)] text-[var(--site-ink)] lg:order-none lg:col-span-6`}
            >
              <figcaption className={CAP}>Adversarial tests on what survived</figcaption>
              <ul className="list-none">
                {RUN.stress.map((test, i) => (
                  <li key={i} className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-4)] last:border-b-0">
                    <div className="flex items-baseline justify-between gap-[var(--space-3)]">
                      <span className="capitalize">{test.scenario}</span>
                      <span className="font-display text-[length:var(--site-lead)] nums-tabular">
                        {Math.round(test.survivalRate * 100)}%
                      </span>
                    </div>
                    <span aria-hidden="true" className="mt-[var(--space-2)] block h-[var(--space-2)] overflow-hidden rounded-full bg-[var(--site-surface)]">
                      <span className="block h-full rounded-full bg-[var(--site-accent)]" style={{ width: `${test.survivalRate * 100}%` }} />
                    </span>
                    <p className="mt-[var(--space-3)] text-[var(--site-muted)]">
                      {test.failureMode || 'This test returned a rate with no prose. Shown as it came back.'}
                    </p>
                  </li>
                ))}
              </ul>
            </figure>
            <div className="lg:col-span-5 lg:col-start-8">
              <Heading id="stress-h" lines={['Then it is', 'attacked.']} />
              <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
                What survives critique is run against adversarial scenarios. Each test reports how
                much of the position held, and the failure it found. Both tests from this run are
                shown as they came back.
              </p>
            </div>
          </div>
        </section>

        {/* ── Synthesis ── */}
        <section
          id="synthesis"
          aria-labelledby="synthesis-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] scroll-mt-[var(--space-20)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <div className="lg:col-span-4">
            <Heading id="synthesis-h" lines={['The answer,', 'with its record.']} />
            <p className={`mt-[var(--space-6)] max-w-[40ch] ${BODY}`}>
              Each claim carries a label: verified, hypothesis or unknown. Switch the record off and
              the words are unchanged; what goes is every means of checking them.
            </p>
          </div>
          <div data-reveal className="min-w-0 lg:col-span-8">
            <ApparatusToggle />
          </div>
        </section>

        {/* ── Interface ── */}
        <section id="api" aria-labelledby="api-h" className={SECTION}>
          <div className="lg:col-span-5">
            <Heading id="api-h" lines={['It comes back', 'as JSON.']} />
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              Everything on this page is a field in the run response: sources, positions, scores,
              bias flags, survival rates and the token count. Call it over HTTP, from the TypeScript
              SDK, or as a tool through the MCP server. {CAPABILITIES.methods} reasoning methods,{' '}
              {CAPABILITIES.presets} presets, {CAPABILITIES.routableModels}+ models.
            </p>
            <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
              <Link href="/developers" className={`site-link ${BODY}`}>
                For developers
              </Link>
              <Link href="/docs" className={`site-link ${BODY}`}>
                Read the docs
              </Link>
            </div>
          </div>
          <figure data-ui data-reveal className={`${FIGURE} flex flex-col bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7`}>
            <figcaption className={CAP}>The same run, over the API</figcaption>
            <pre tabIndex={0} className="flex-1 overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]">
              <code>{`curl https://reasoner.app/api/agent/run/sync \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "Should a 12-person startup …",
       "preset": "${RUN.preset}"}'

# → { "synthesis": …, "scores": [ … ],
#     "stress_tests": [ … ], "sources": [ … ],
#     "total_cost_usd": ${RUN.ledger.costUsd.toFixed(4)} }`}</code>
            </pre>
            <dl className="grid grid-cols-2 border-t border-[var(--site-line)] nums-tabular sm:grid-cols-4">
              {[
                { term: 'Wall clock', value: `${RUN.ledger.seconds.toFixed(1)}s` },
                /* Locale pinned: a bare toLocaleString() follows the SERVER's
                   locale, which turned 10,297 into "10.297" on a Greek host. */
                { term: 'Tokens in', value: RUN.ledger.tokensIn.toLocaleString('en-US') },
                { term: 'Tokens out', value: RUN.ledger.tokensOut.toLocaleString('en-US') },
                { term: 'Cost', value: `$${RUN.ledger.costUsd.toFixed(4)}` },
              ].map(({ term, value }) => (
                <div key={term} className="px-[var(--space-4)] py-[var(--space-3)]">
                  <dt className="text-[var(--site-muted)]">{term}</dt>
                  <dd className="font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
          </figure>
        </section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] pb-[var(--space-24)]">
          <Heading id="close-h" lines={['Your question,', 'same treatment.']} />
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            The same phases, the same scoring and the same record at the end: a decision you can hand
            to someone else with the working attached. {RUN_MODELS.length} models answered this one for
            ${RUN.ledger.costUsd.toFixed(4)}.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/chat" className="site-button">
              Run your own question
            </Link>
            <Link href="/security" className={`site-link ${BODY}`}>
              Where your data goes
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
