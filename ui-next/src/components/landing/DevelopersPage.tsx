import Link from 'next/link';
import { Aside, Body, Heading, Lede, Section } from '@/components/landing/prose';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { CAPABILITIES } from '@/lib/capabilities.generated';

/**
 * The developer argument, for the reader who will never open the chat UI.
 *
 * It is set as the same kind of document as /capabilities — marginal §
 * markers, one claim per section, the shared prose chrome — because a
 * developer page written in a different voice reads as a different product,
 * and the claim being made here is that there is only one product behind
 * every door.
 *
 * That claim is the spine: MCP, the HTTP surface, and the command line are
 * driving adapters onto one application layer, so a run started from Claude
 * Desktop is routed, metered, and idempotency-guarded exactly like one
 * started from curl. Nothing on this page may describe a capability that
 * holds on only one of them — and where one genuinely differs (the CLI bills
 * against the instance's own provider keys rather than credits), the section
 * says so rather than smoothing it over.
 *
 * Copy discipline, as on the other marketing pages: figures come from
 * `capabilities.generated.ts`, which is regenerated from the live registry on
 * each commit, and every endpoint, tool name, and status code named here is
 * checked against src/reasoner/api/ and docs/MCP.md rather than typed from
 * memory. The prose reference for all of it is /docs/mcp and
 * /docs/agent-integration — this page argues, those pages instruct, and a
 * detail that needs updating belongs in the docs registry rather than here.
 */

/* ── Content ──────────────────────────────────────────────────────── */

/**
 * The MCP tool surface, verbatim from src/reasoner/api/mcp/tools.py. The
 * paid/free split is the load-bearing part: the read-only four are what let
 * an agent price and preview a call before committing to one that bills.
 */
const MCP_TOOLS = [
  {
    name: 'reasoner_run',
    cost: 'Paid',
    desc: 'Runs a pipeline and reports a progress notification per phase.',
  },
  {
    name: 'reasoner_followup',
    cost: 'Paid',
    desc: 'Continues a thread with the prior synthesis as context.',
  },
  {
    name: 'reasoner_gate',
    cost: 'Free',
    desc: 'Shows how a problem would be routed, without running it.',
  },
  {
    name: 'reasoner_estimate',
    cost: 'Free',
    desc: 'Tokens, dollars, and duration for a problem and preset.',
  },
  {
    name: 'reasoner_presets',
    cost: 'Free',
    desc: 'The live preset catalogue, with method and primary model.',
  },
  {
    name: 'reasoner_health',
    cost: 'Free',
    desc: 'Liveness and dependency status, public detail only.',
  },
];

/**
 * What an agent can read before it has ever been told anything about this
 * API. Every row is a live endpoint or route in this app, not a document
 * about one.
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
  { code: '402', desc: 'Credits exhausted. Stop — a retry cannot succeed.' },
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
#     "claim_labels": { "The deploy pipeline is the bottleneck": "VERIFIED" },
#     "open_questions": [ … ], "action_blueprint": [ … ],
#     "total_cost_usd": 0.0191, "errors": [] }`;

/* ── Page ─────────────────────────────────────────────────────────── */

/** Shared by the code exhibits, so none of them drifts into its own idiom. */
function Code({ children, label }: { children: string; label: string }) {
  return (
    <figure className="mt-[var(--space-8)]">
      <figcaption className="font-sans text-[length:var(--text-2xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
        {label}
      </figcaption>
      <pre className="mt-[var(--space-3)] overflow-x-auto border border-[var(--border)] bg-[var(--surface)] p-[var(--space-6)] font-mono text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-2)]">
        <code>{children}</code>
      </pre>
    </figure>
  );
}

export default function DevelopersPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content">
        {/* ── Masthead ───────────────────────────────────────────
            Short, like /capabilities. The reader arriving here wants to
            know whether this is callable and what comes back, and §1
            answers both in the first screen after it. */}
        <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-48)]">
          <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div>
              <p className="mt-[var(--space-1)] font-sans text-[length:var(--text-2xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
                Developers
              </p>
            </div>
            <div className="min-w-0">
              <h1 className="max-w-[20ch] text-balance font-serif text-[length:var(--text-4xl)] font-normal leading-[var(--lh-display)] sm:text-[length:var(--text-6xl)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                An answer your code can act on.
              </h1>
              <p className="prose-measure mt-[var(--space-6)] text-[length:var(--text-2xl)] leading-[var(--lh-body)] text-[var(--text-2)]">
                A single model returns prose, and your program has to decide how much of it to
                believe. Reasoner returns a synthesis in which every claim is already labelled
                VERIFIED, HYPOTHESIS, or UNKNOWN — which is what makes the output safe to branch
                on, store, or hand to another model.
              </p>
              <Aside href="/docs/agent-integration">Read the integration guide &rarr;</Aside>
            </div>
          </div>
        </header>

        {/* ── §1 MCP ────────────────────────────────────────────
            Leads because it is the shortest path from nothing to a
            working call: a config block, no client code. */}
        <Section id="mcp" marker="§1" name="MCP">
          <Heading>If your host speaks MCP, there is no client to write.</Heading>
          <Lede>
            Reasoner ships a Model Context Protocol server. Claude Desktop, Claude Code, and most
            current agent frameworks pick it up from a config block and expose six tools directly
            — no HTTP client, no stream parser, no schema to hand-copy.
          </Lede>

          <Code label="Host MCP config">{MCP_CONFIG}</Code>

          <Body>
            A blocking twenty-to-ninety-second tool call is a bad experience when nothing comes
            back until it ends, so the two paid tools emit a progress notification per pipeline
            phase. The host can say <em>Phase 3: Critique</em> instead of sitting on a spinner.
          </Body>

          <dl className="mt-[var(--space-10)] grid gap-x-[var(--space-8)] gap-y-[var(--space-5)] sm:grid-cols-2">
            {MCP_TOOLS.map(({ name, cost, desc }) => (
              <div key={name} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="flex items-baseline gap-[var(--space-3)]">
                  <span className="font-mono text-[length:var(--text-md)] leading-[var(--lh-ui)] text-[var(--text)]">
                    {name}
                  </span>
                  <span className="font-sans text-[length:var(--text-2xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                    {cost}
                  </span>
                </dt>
                <dd className="mt-[var(--space-1)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            There is no admin tool, no key-management tool, and no data-export tool on this
            surface, and there will not be. That boundary is held by a test rather than by a
            convention, so an addition that crosses it fails the build.
          </Body>

          <Aside href="/docs/mcp">Setup, the tool reference, and the HTTP transport &rarr;</Aside>
        </Section>

        {/* ── §2 HTTP ───────────────────────────────────────────── */}
        <Section id="http" marker="§2" name="HTTP">
          <Heading>Or one POST, and one JSON body back.</Heading>
          <Lede>
            The HTTP surface is the same pipeline through a different door.{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">/api/agent/run/sync</code>{' '}
            blocks and returns one result; <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">/api/agent/run</code>{' '}
            streams the phases as Server-Sent Events. Neither is the lesser path — the sync
            endpoint is the streaming pipeline with the collapsing done for you, server-side.
          </Lede>

          <Code label="One call, one result">{CURL}</Code>

          <Body>
            The labels are the payload. <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">claim_labels</code>{' '}
            says what is carried by a source outside the model and what is only asserted;{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">open_questions</code> is
            the run telling you what it could not settle; each{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">action_blueprint</code>{' '}
            step carries a go-criterion you can check later. An integration that flattens those
            back into undifferentiated prose has thrown away the reason it called.
          </Body>
          <Body>
            TypeScript callers can skip the plumbing:{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">@reasoner/sdk</code>{' '}
            exposes <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">runToCompletion()</code>,
            which returns the same fields already parsed.
          </Body>

          <Aside href="/docs/api-reference">The endpoint reference &rarr;</Aside>
        </Section>

        {/* ── §3 Command line ───────────────────────────────────
            Third because it is the door with the fewest callers and
            the most reach: it is what a cron job, a CI step, or a
            host application that would rather not run a server uses.
            Both halves are real entry points — main.py's argparse
            surface and reasoner.headless.ask() — and headless goes
            through the same parser, so a flag documented for one is
            true of the other. */}
        <Section id="cli" marker="§3" name="Command line">
          <Heading>Or no network at all.</Heading>
          <Lede>
            The same pipeline runs from a shell. A scheduled job, a CI step, or a batch over a
            file of questions needs neither a server nor a key exchange — point the CLI at a
            problem and an output path, and the full run state comes back as JSON.
          </Lede>

          <Code label="Headless">{CLI}</Code>

          <Body>
            A long run can be saved mid-flight and resumed from the state file, which is what makes
            an interrupted batch recoverable rather than repayable.{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">--list-presets</code> and{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">--list-models</code> print
            the live catalogues with their key status, and{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">--sequential</code> walks
            the phases one model at a time for providers that rate-limit hard.
          </Body>
          <Body>
            A host application that would rather not shell out can import the pipeline instead.{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">headless.ask()</code>{' '}
            returns the routing decision alongside the result, so your code can tell a one-second
            direct answer from a full run and treat them differently.
          </Body>
          <Body>
            This is the one door that does not run on credits. A local run calls the model
            providers with the keys in your own environment and is billed by them, not by us —
            which is the trade for having no account, no network hop, and no ledger in the middle.
          </Body>
        </Section>

        {/* ── §4 Discovery ──────────────────────────────────────── */}
        <Section id="discovery" marker="§4" name="Discovery">
          <Heading>Fetch the tool definition rather than copying one.</Heading>
          <Lede>
            A hand-copied tool schema is a schema that will drift. Ours is generated from the same
            request model the API validates against, and served live, so an agent that fetches it
            once per session cannot register a call this API no longer accepts.
          </Lede>

          <dl className="mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-4)] sm:grid-cols-2">
            {DISCOVERY.map(({ path, desc }) => (
              <div key={path} className="border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-mono text-[length:var(--text-md)] leading-[var(--lh-ui)] text-[var(--text)]">
                  {path}
                </dt>
                <dd className="mt-[var(--space-1)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>

          <Body>
            Preset ids are data, not constants. There are {CAPABILITIES.presets} of them across{' '}
            {CAPABILITIES.methods} methods and{' '}
            {CAPABILITIES.routableModels.toLocaleString('en-US')} routable models, and the
            catalogue moves independently of the tool schema — which is why an integration that
            hardcodes a preset name is the one that breaks.
          </Body>
        </Section>

        {/* ── §5 Before you spend ───────────────────────────────── */}
        <Section id="preview" marker="§5" name="Preview">
          <Heading>Two free calls before the one that bills.</Heading>
          <Lede>
            A reasoning run costs real money and takes real time, so both facts are available
            before you commit to either.{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">POST /api/gate</code>{' '}
            returns the route, the method it would use, and a confidence;{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">POST /api/estimate</code>{' '}
            returns tokens, dollars, and duration. Both take the body you were going to send
            anyway.
          </Lede>
          <Body>
            The router shares its cache between the two, so a gate call followed by a real run does
            not pay the routing cost twice. When the gate answers{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">needs_confirmation</code>,
            it is unsure — a good moment for an agent to ask its own caller rather than spend on
            its own judgement.
          </Body>
          <Body>
            The gate is also what stops you overpaying by default: a question with one determinate
            answer is routed to a direct reply in about a second, and you are not billed for
            reasoning you did not need.
          </Body>

          <Aside href="/docs/credits">How runs are metered &rarr;</Aside>
        </Section>

        {/* ── §6 Billing and retries ────────────────────────────── */}
        <Section id="metering" marker="§6" name="Metering">
          <Heading>Same billing through every door.</Heading>
          <Lede>
            MCP and HTTP are two adapters onto one application layer. A run started from Claude
            Desktop resolves auth, guards idempotency, and settles credits exactly like one started
            from curl — there is no second product with its own accounting to reconcile against.
          </Lede>
          <Body>
            Runs settle after they complete, from the actual cost on the terminal frame. A run that
            fails costs nothing. Send a{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">client_run_id</code> on
            every call: it is both the duplicate-run guard and the credit idempotency key, so a
            dropped stream is resumed by reconnecting with the same id rather than by paying for
            the question twice. A pipeline is capped at 600 seconds — set the client timeout above
            that, or you will abandon runs you have already paid for.
          </Body>

          <dl className="nums-tabular mt-[var(--space-8)] grid gap-x-[var(--space-8)] gap-y-[var(--space-4)] sm:grid-cols-2">
            {STATUSES.map(({ code, desc }) => (
              <div key={code} className="flex items-baseline gap-[var(--space-4)] border-t border-[var(--border)] pt-[var(--space-3)]">
                <dt className="font-mono text-[length:var(--text-md)] leading-[var(--lh-ui)] text-[var(--text)]">
                  {code}
                </dt>
                <dd className="text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                  {desc}
                </dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* ── §7 Keys ───────────────────────────────────────────── */}
        <Section id="keys" marker="§7" name="Keys">
          <Heading>One key per agent, scoped down.</Heading>
          <Lede>
            Keys are minted in settings, shown once, and carry scopes. A default read-only key runs
            pipelines and reads the catalogues, which is everything an agent needs and nothing it
            does not. Give each agent its own: revoking one then costs you one agent, and the
            ledger attributes spend per key.
          </Lede>
          <Body>
            Keep the key out of the prompt — an agent that can read its own credentials can leak
            them into a transcript. Everything you send is sanitised before it reaches a model, and
            every phase is told that text arriving from outside is data rather than instruction,
            but neither of those is authorisation: text your agent forwards on someone else&rsquo;s
            behalf is still text from someone else.
          </Body>
          <Body>
            The same endpoints, the same{' '}
            <code className="font-mono text-[length:var(--text-sm)] text-[var(--text-2)]">rsn_live_</code> keys, and
            the same metering work on a self-hosted instance. The source is available under a
            Business Source License that converts to Apache-2.0 in 2030, and the stack runs against
            your own Postgres and Valkey.
          </Body>

          <Aside href="/docs/api-keys">Scopes, rotation, and revocation &rarr;</Aside>
        </Section>

        {/* ── Close ─────────────────────────────────────────────── */}
        <section className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] py-[var(--section-y)]">
          <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div aria-hidden="true" />
            <div className="min-w-0">
              <Heading>Delegate the calls you would not trust one model with.</Heading>
              <Lede>
                The decisions where a confident wrong answer costs something, and where you want
                the disagreement back rather than a summary of it.
              </Lede>
              <div className="mt-[var(--space-10)] flex flex-wrap items-center gap-[var(--space-4)]">
                <Link
                  href="/docs/mcp"
                  className="btn-lift flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] font-sans text-[length:var(--text-md)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
                >
                  Set up the MCP server
                </Link>
                <Link
                  href="/docs/api-reference"
                  className="link-smooth flex min-h-[var(--space-12)] items-center font-sans text-[length:var(--text-md)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] underline decoration-[var(--border-strong)] underline-offset-4 hover:text-[var(--text)]"
                >
                  Read the API reference
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
