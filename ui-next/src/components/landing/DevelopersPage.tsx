import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import {
  ArgumentBody as Body,
  ArgumentSection as Section,
  BODY,
  CAP,
  FIGURE,
  HEAD,
  More,
  ROW,
} from '@/components/site/ArgumentSection';
import { CAPABILITIES } from '@/lib/capabilities.generated';

/**
 * /developers in the site world "The product performs": the developer
 * argument, for the reader who will never open the chat UI.
 *
 * The spine is that there is one product behind every door: MCP, the HTTP
 * surface, and the command line are driving adapters onto one application
 * layer, so a run started from Claude Desktop is routed, metered, and
 * idempotency-guarded exactly like one started from curl. Nothing on this page
 * may describe a capability that holds on only one of them, and where one
 * genuinely differs (the CLI bills against the instance's own provider keys
 * rather than credits), the section says so.
 *
 * Copy discipline: figures come from `capabilities.generated.ts`, and every
 * endpoint, tool name, and status code is checked against src/reasoner/api/
 * and docs/MCP.md rather than typed from memory. This page argues; /docs/mcp
 * and /docs/agent-integration instruct.
 */

/* ── Content ──────────────────────────────────────────────────────── */

/**
 * The MCP tool surface, verbatim from src/reasoner/api/mcp/tools.py. The
 * paid/free split is the load-bearing part: the read-only four let an agent
 * price and preview a call before committing to one that bills.
 */
const MCP_TOOLS = [
  { name: 'reasoner_run', cost: 'Paid', desc: 'Runs a pipeline, with a progress notification per phase.' },
  { name: 'reasoner_followup', cost: 'Paid', desc: 'Continues a thread with the prior synthesis as context.' },
  { name: 'reasoner_gate', cost: 'Free', desc: 'Shows how a problem would be routed, without running it. 200 calls a day.' },
  { name: 'reasoner_estimate', cost: 'Free', desc: 'Tokens, dollars, and duration for a problem and preset.' },
  { name: 'reasoner_presets', cost: 'Free', desc: 'The live preset catalogue, with method and primary model.' },
  { name: 'reasoner_health', cost: 'Free', desc: 'Liveness and dependency status, public detail only.' },
];

/**
 * What an agent can read before it has been told anything about this API.
 * Every row is a live endpoint or route in this app, not a document about one.
 */
const DISCOVERY = [
  { path: 'GET /api/agent/tools', desc: 'Tool definitions, in Anthropic or OpenAI shape. Cacheable.' },
  { path: 'GET /openapi.json', desc: 'The full schema, for every endpoint.' },
  { path: 'GET /api/presets', desc: 'Every preset with its method, tier, and cost band.' },
  { path: 'GET /api/models', desc: 'Registered models, with vendor and pricing.' },
  { path: '/llms.txt', desc: 'A map of this documentation, written for a model.' },
  { path: '/llms-full.txt', desc: 'The entire documentation corpus, in one file.' },
];

/** The four statuses whose correct handling is not guessable from the number. */
const STATUSES = [
  { code: '402', desc: 'Credits exhausted. Stop: a retry cannot succeed.' },
  { code: '409', desc: 'Duplicate client_run_id. Reuse the first run’s result; you were not billed twice.' },
  { code: '429', desc: 'Back off for Retry-After. X-RateLimit-Remaining is on every response.' },
  { code: '503', desc: 'A dependency is down. Retry with backoff.' },
];

const MCP_CONFIG = `{
  "mcpServers": {
    "reasoner": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": { "REASONER_API_KEY": "rsn_live_..." }
    }
  }
}`;

const CLI = `# One run, exported as JSON.
python main.py \\
  --problem "Should we migrate off our monolith?" \\
  --preset debate-premium \\
  --output result.json

# In-process (Python), no server in between.
from reasoner import headless
result = await headless.ask("...", preset="research-budget")`;

const CURL = `curl -s https://reasoner.app/api/agent/run/sync \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "Should we migrate off our monolith?"}'

# → { "synthesis": …,
#     "claim_labels": {
#       "The deploy pipeline is the bottleneck": "VERIFIED" },
#     "open_questions": [ … ], "action_blueprint": [ … ],
#     "total_cost_usd": 0.0191, "errors": [] }`;

const PRE = 'overflow-x-auto px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]';

/* ── Page ─────────────────────────────────────────────────────────── */

export default function DevelopersPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), one call and what comes back (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>An answer your</span>
              </span>
              <span className="site-line">
                <span>code can act on.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Every claim comes back labelled verified, hypothesis or unknown, so your program can
                branch on it, store it, or hand it to another model.
              </p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>
                One pipeline behind three doors: an MCP server, an HTTP API, and the command line.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <Link href="/docs/mcp" className="site-button">
                  Set up the MCP server
                </Link>
                <Link href="/docs/agent-integration" className={`site-link ${BODY}`}>
                  Read the integration guide
                </Link>
              </div>
            </div>
          </div>

          {/* min-w-0: without it the code's longest line sets the grid track and widens the page. */}
          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>One call, one result</figcaption>
              <pre className={PRE}>
                <code>{CURL}</code>
              </pre>
            </figure>
          </div>
        </header>

        {/* ── MCP: leads because it is the shortest path from nothing to a
            working call: a config block, no client code. ── */}
        <Section
          id="mcp"
          lines={['Speaks MCP?', 'No client to write.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Host MCP config</figcaption>
              <pre className={`border-b border-[var(--site-line)] ${PRE}`}>
                <code>{MCP_CONFIG}</code>
              </pre>
              <p className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold">
                Six tools
              </p>
              <dl>
                {MCP_TOOLS.map(({ name, cost, desc }) => (
                  <div key={name} className={ROW}>
                    <dt className="flex flex-wrap items-baseline justify-between gap-[var(--space-3)]">
                      <code>{name}</code>
                      <span className={cost === 'Free' ? 'font-semibold text-[var(--site-accent)]' : 'text-[var(--site-muted)]'}>{cost}</span>
                    </dt>
                    <dd className="text-[var(--site-muted)]">{desc}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            Reasoner ships a Model Context Protocol server. Claude Desktop, Claude Code, and most
            current agent frameworks pick it up from a config block and expose six tools directly: no
            HTTP client, no stream parser, no schema to hand-copy.
          </Body>
          <Body>
            A twenty-to-ninety-second tool call is a bad experience when nothing comes back until it
            ends, so the two paid tools emit a progress notification per pipeline phase. The host can
            say <em>Phase 3: Critique</em> instead of sitting on a spinner.
          </Body>
          <Body>
            There is no admin tool, no key-management tool, and no data-export tool on this surface,
            and there will not be. That boundary is held by a test, so an addition that crosses it
            fails the build.
          </Body>
          <More href="/docs/mcp">Setup, the tool reference, and the HTTP transport</More>
        </Section>

        {/* ── HTTP: the hero already shows the call. ── */}
        <Section id="http" lines={['Or one POST,', 'one JSON back.']} field>
          <Body>
            The HTTP surface is the same pipeline through a different door.{' '}
            <code>/api/agent/run/sync</code> blocks and returns one result;{' '}
            <code>/api/agent/run</code> streams the phases as Server-Sent Events. Neither is the lesser
            path: the sync endpoint is the streaming pipeline with the collapsing done server-side.
          </Body>
          <Body>
            The labels are the payload. <code>claim_labels</code> says what is carried by a source
            outside the model and what is only asserted; <code>open_questions</code> is the run telling
            you what it could not settle; each <code>action_blueprint</code> step carries a
            go-criterion you can check later. An integration that flattens those back into prose has
            thrown away the reason it called.
          </Body>
          <Body>
            TypeScript callers can skip the plumbing: <code>@reasoner/sdk</code> exposes{' '}
            <code>runToCompletion()</code>, which returns the same fields already parsed.
          </Body>
          <More href="/docs/api-reference">The endpoint reference</More>
        </Section>

        {/* ── Command line: both halves are real entry points (main.py's
            argparse surface and reasoner.headless.ask()), and headless goes
            through the same parser, so a flag documented for one is true of
            the other. ── */}
        <Section
          id="cli"
          lines={['Or no network', 'at all.']}
          figure={
            <figure data-ui className={`${FIGURE} flex flex-col`}>
              <figcaption className={CAP}>Headless</figcaption>
              <pre className={`flex-1 ${PRE}`}>
                <code>{CLI}</code>
              </pre>
            </figure>
          }
        >
          <Body>
            The same pipeline runs from a shell. A scheduled job, a CI step, or a batch over a file of
            questions needs neither a server nor a key exchange: point the CLI at a problem and an
            output path, and the full run state comes back as JSON.
          </Body>
          <Body>
            A long run can be saved mid-flight and resumed from the state file, so an interrupted batch
            is recoverable rather than repayable. <code>--list-presets</code> and{' '}
            <code>--list-models</code> print the live catalogues with their key status, and{' '}
            <code>--sequential</code> walks the phases one model at a time for providers that rate-limit
            hard. A host application can import the pipeline instead: <code>headless.ask()</code>{' '}
            returns the routing decision alongside the result.
          </Body>
          <Body>
            This is the one door that does not run on credits. A local run calls the model providers
            with the keys in your own environment and is billed by them, not by us: the trade for
            having no account, no network hop, and no ledger in the middle.
          </Body>
        </Section>

        {/* ── Discovery ── */}
        <Section
          id="discovery"
          lines={['Fetch the tools,', 'do not copy them.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Readable before you have been told anything</figcaption>
              <dl>
                {DISCOVERY.map(({ path, desc }) => (
                  <div key={path} className={ROW}>
                    <dt>
                      <code>{path}</code>
                    </dt>
                    <dd className="text-[var(--site-muted)]">{desc}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            A hand-copied tool schema is a schema that will drift. Ours is generated from the same
            request model the API validates against, and served live, so an agent that fetches it once
            per session cannot register a call this API no longer accepts.
          </Body>
          <Body>
            Preset ids are data, not constants. There are {CAPABILITIES.presets} of them across{' '}
            {CAPABILITIES.methods} methods and {CAPABILITIES.routableModels.toLocaleString('en-US')}{' '}
            routable models, and the catalogue moves independently of the tool schema, which is why an
            integration that hardcodes a preset name is the one that breaks.
          </Body>
        </Section>

        {/* ── Before you spend ── */}
        <Section id="preview" lines={['Two free calls', 'before one bills.']}>
          <Body>
            A reasoning run costs real money and takes real time, so both facts are available before
            you commit. <code>POST /api/gate</code> returns the route, the method it would use, and a
            confidence; <code>POST /api/estimate</code> returns tokens, dollars, and duration. Both take
            the body you were going to send anyway. The gate is free up to 200 calls a day per account.
          </Body>
          <Body>
            The router shares its cache between the two, so a gate call followed by a real run does not
            pay the routing cost twice. When the gate answers <code>needs_confirmation</code>, it is
            unsure: a good moment for an agent to ask its own caller rather than spend on its own
            judgement.
          </Body>
          <Body>
            The gate also stops you overpaying by default: a question with one determinate answer is
            routed to a direct reply in about a second, and you are not billed for reasoning you did not
            need.
          </Body>
          <More href="/docs/credits">How runs are metered</More>
        </Section>

        {/* ── Billing and retries ── */}
        <Section
          id="metering"
          lines={['Same billing', 'through every door.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Statuses you cannot guess from the number</figcaption>
              <dl>
                {STATUSES.map(({ code, desc }) => (
                  <div key={code} className={`grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-[var(--space-4)] ${ROW}`}>
                    <dt className="font-display text-[length:var(--site-lead)] nums-tabular">{code}</dt>
                    <dd>{desc}</dd>
                  </div>
                ))}
              </dl>
            </figure>
          }
        >
          <Body>
            MCP and HTTP are two adapters onto one application layer. A run started from Claude Desktop
            resolves auth, guards idempotency, and settles credits exactly like one started from curl.
          </Body>
          <Body>
            Runs settle after they end, from their actual cost; a run that stops early pays only for
            what it spent. Send a <code>client_run_id</code> on every call: a repeat of a run in flight
            or finished gets 409 instead of running twice. A pipeline is capped at 600 seconds, so set
            the client timeout above that, or you will abandon runs you have already paid for.
          </Body>
        </Section>

        {/* ── Keys ── */}
        <Section id="keys" lines={['One key per agent,', 'scoped down.']}>
          <Body>
            Keys are minted in settings, shown once, and carry scopes. A default key runs pipelines and
            reads the catalogues: everything an agent needs and nothing it does not. Give each agent its
            own, so revoking one costs you one agent, and the ledger attributes spend per key.
          </Body>
          <Body>
            Keep the key out of the prompt: an agent that can read its own credentials can leak them
            into a transcript. Everything you send is sanitised before it reaches a model, and every
            phase is told that outside text is data rather than instruction, but neither is
            authorisation: text your agent forwards on someone else&rsquo;s behalf is still text from
            someone else.
          </Body>
          <Body>
            The same endpoints, the same <code>rsn_live_</code> keys, and the same metering work on a
            self-hosted instance. The source is available under a Business Source License that converts
            to Apache-2.0 in 2030, and the stack runs against your own Postgres and Valkey.
          </Body>
          <More href="/docs/api-keys">Scopes, rotation, and revocation</More>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">Delegate the calls</span>
            <span className="block">you would not trust.</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            The decisions where a confident wrong answer costs something, and where you want the
            disagreement back rather than a summary of it.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/docs/mcp" className="site-button">
              Set up the MCP server
            </Link>
            <Link href="/docs/api-reference" className={`site-link ${BODY}`}>
              Read the API reference
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
