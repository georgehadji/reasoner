# `@reasoner/sdk`

TypeScript client for the [Reasoner](https://reasoner.app) API — multi-model reasoning pipelines, either streamed over Server-Sent Events or collapsed to one JSON object server-side.

Zero runtime dependencies. Runs on Node 20+, Bun, Deno, browsers, and edge runtimes.

## Why this exists

`POST /api/run` is an SSE stream, not a JSON request. Without a client, every caller writes the same four things: an SSE parser that tolerates unknown event types, `total_cost_usd` extraction from the terminal `done` frame, idempotency-key handling for `client_run_id`, and backoff on `429`/`503`. That is the whole job of this package — plus `runSync()`, for callers who would rather the server do that folding and never see a stream at all.

## Which surface should I use?

| I want... | Use | Notes |
| --- | --- | --- |
| One call, one answer, no SSE parser | `client.runSync(params)` | Hits `POST /api/agent/run/sync`. Simplest option. |
| The answer, but I already have a stream-friendly client | `client.runToCompletion(params)` | Same result shape as `runSync`, folded client-side; keeps `RunSummary.events`. |
| Per-phase progress as it happens | `client.run(params)` | Async iterable of `ReasonerEvent`. |
| A host that speaks [MCP](https://modelcontextprotocol.io) (Claude Desktop, Claude Code) | Skip this package | Reasoner ships an MCP server — see [`docs/MCP.md`](https://github.com/georgehadji/reasoner/blob/main/docs/MCP.md) in the main repo. Same pipeline, same billing, no HTTP client code. |

`runSync` and `runToCompletion` return the identical `RunSummary` shape, so switching between them is a one-line change.

## Install

```bash
npm install @reasoner/sdk
```

## Quickstart

```ts
import { ReasonerClient } from '@reasoner/sdk';

const client = new ReasonerClient({ apiKey: process.env.REASONER_API_KEY });

const result = await client.runToCompletion({
  problem: 'Should we migrate off our monolith?',
  preset: 'auto-budget',
});

console.log(result.synthesis);
console.log(`$${result.costUsd.toFixed(4)} · ${result.tokens.total} tokens · ${result.modelsUsed.length} models`);
```

Get an API key from [reasoner.app](https://reasoner.app) account settings. Keys look like `rsn_live_…`, are shown exactly once, and should be read from the environment — never committed.

`runToCompletion` streams internally and folds the result client-side. If you would rather the server do that folding — one request, one response, no SSE parser touches your code — use `runSync` instead:

```ts
const result = await client.runSync({ problem: 'Should we migrate off our monolith?' });
console.log(result.synthesis);
```

Same `RunSummary` shape either way; `result.events` is empty from `runSync` since there was never a stream to keep.

## Streaming

`run()` returns an async iterable. Nothing is sent until you start iterating, and leaving the loop aborts the transfer.

```ts
import { ReasonerClient, isEvent } from '@reasoner/sdk';

const client = new ReasonerClient({ apiKey: process.env.REASONER_API_KEY });

for await (const event of client.run({ problem: 'Why did our launch underperform?' })) {
  if (isEvent(event, 'method_selected')) {
    console.log(`routing → ${event.method} (${event.confidence})`);
  }
  if (isEvent(event, 'phase_complete')) {
    console.log(`phase ${event.phase} · ${event.name}`);
  }
  if (isEvent(event, 'done')) {
    console.log(`cost $${event.total_cost_usd}`);
  }
}
```

### The event set is open

The API adds new event types **without a version bump**. Narrow with `isEvent()` and ignore anything you do not recognise — never `switch` exhaustively on `type`, and never treat an unknown event as an error.

```ts
for await (const event of client.run({ problem })) {
  if (isEvent(event, 'done')) handleDone(event);
  // Everything else, known or not, falls through harmlessly.
}
```

### Aborting

`break` out of the loop, or pass a signal:

```ts
const controller = new AbortController();
setTimeout(() => controller.abort(), 30_000);

for await (const event of client.run({ problem }, { signal: controller.signal })) {
  // …
}
```

Aborting stops the *delivery*, not the run. The pipeline continues server-side and is still charged for what it spends.

## Cost control

Estimate before committing:

```ts
const estimate = await client.estimate({ problem, preset: 'debate-premium' });
console.log(`~$${estimate.estimated_cost_usd} · ~${estimate.estimated_duration_seconds}s`);
```

Ask the router what it would do, then lock the choice in without paying for routing twice:

```ts
const decision = await client.gate({ problem });

if (decision.needs_confirmation) {
  // Low confidence — worth asking a human before spending.
  console.log(decision.method, decision.reasoning, decision.alternatives);
}

const result = await client.runToCompletion({
  problem,
  preset: decision.preset ?? 'auto-budget',
  force_pipeline: true,
});
```

Check the balance:

```ts
const { balance, tier, monthly_allowance } = await client.credits();
```

## Idempotency

Every run carries a `client_run_id`. It guards against duplicate runs *and* keys credit settlement, so one id is charged at most once. The SDK generates one per call; supply your own when the caller owns the identity:

```ts
await client.runToCompletion({ problem, client_run_id: `job-${jobId}` });
```

Retries inside the SDK deliberately reuse the same id. Submitting an id that is already in flight raises `DuplicateRunError` — read the original run's result rather than resubmitting under a fresh id.

## Errors

Each documented status maps to a class:

| Status | Class | Meaning |
| --- | --- | --- |
| 400 / 422 | `BadRequestError` | Payload rejected; `message` names the field |
| 401 | `AuthenticationError` | Missing, invalid, or revoked key |
| 402 | `InsufficientCreditsError` | Balance exhausted — top up |
| 403 | `PermissionError` | Key lacks the required scope |
| 409 | `DuplicateRunError` | `client_run_id` already in flight |
| 429 | `RateLimitError` | Rate limited; carries `retryAfterMs` |
| 5xx | `ServerError` | Dependency failure — retryable |
| — | `ConnectionError` | Network, DNS, TLS, or timeout |
| — | `AbortError` | Caller aborted |

```ts
import { InsufficientCreditsError, RateLimitError } from '@reasoner/sdk';

try {
  await client.runToCompletion({ problem });
} catch (error) {
  if (error instanceof InsufficientCreditsError) await topUp();
  else if (error instanceof RateLimitError) await sleep(error.retryAfterMs ?? 60_000);
  else throw error;
}
```

`429`, `502`, `503`, and `504` are retried automatically (default 2 attempts, honouring `Retry-After`). `402` and `409` are never retried — neither resolves on its own. A stream that fails *after* bytes have arrived is not retried either, since SSE cannot be resumed mid-flight.

## Configuration

```ts
new ReasonerClient({
  apiKey: process.env.REASONER_API_KEY, // defaults to REASONER_API_KEY
  baseUrl: 'https://reasoner.app',      // 'http://127.0.0.1:8003' for a local backend
  maxRetries: 2,
  timeoutMs: 600_000,                   // full runs are slow by design
  headers: {},
  fetch: globalThis.fetch,
});
```

## API

| Method | Endpoint | Returns |
| --- | --- | --- |
| `run(params, opts?)` | `POST /api/run` | `AsyncIterable<ReasonerEvent>` |
| `runFollowup(params, opts?)` | `POST /api/run-followup` | `AsyncIterable<ReasonerEvent>` |
| `runToCompletion(params, opts?)` | `POST /api/run` | `RunSummary` (folded client-side) |
| `runSync(params, opts?)` | `POST /api/agent/run/sync` | `RunSummary` (folded server-side) |
| `gate(params, opts?)` | `POST /api/gate` | `GateResponse` |
| `estimate(params, opts?)` | `POST /api/estimate` | `EstimateResponse` |
| `presets(opts?)` | `GET /api/presets` | `PresetsResponse` |
| `models(opts?)` | `GET /api/models` | `ModelsResponse` |
| `health(opts?)` | `GET /api/health` | dependency status |
| `credits(opts?)` | `GET /api/credits` | balance, tier, allowance |
| `creditLedger(params?, opts?)` | `GET /api/credits/ledger` | `LedgerResponse` |
| `creditPricing(opts?)` | `GET /api/credits/pricing` | `CreditPricingResponse` |

API key management (`/api/account/api-keys`) is deliberately not exposed. Minting credentials belongs in an authenticated browser session, not in a library holding a long-lived key.

`RunSummary` reads `critical_insights`, `action_blueprint`, `open_questions`, and `claim_labels` from the synthesis `phase_complete` payload, which is where the pipeline actually emits them — the `done` frame carries only errors, tokens, duration, and cost.

## Development

```bash
npm install
npm test
npm run typecheck
npm run build
```

Publishing pushes a real package to the public npm registry — `npm publish` is not run by CI automatically. `package.json` targets the `@reasoner` npm scope; that scope must exist and this checkout must be authenticated (`npm whoami`) as a member before `npm publish` (or the `release-sdk` workflow below) will succeed. If `@reasoner` is unavailable, rename the package before the first publish — a scope collision is not something to discover after tagging a release.

### Keeping in sync with the API

The SDK is a second public contract, and nothing in either type checker connects it to the backend. Four things keep it honest.

Two are conventions:

1. **Wire shapes stay `snake_case`**, matching the API reference 1:1, so there is no translation layer to drift. Only SDK-level ergonomics (`baseUrl`, `maxRetries`, `RunSummary`) use `camelCase`.
2. **Server defaults are never duplicated here.** Unset options are omitted from the request body so the backend owns its own defaults.

Two are enforced by tests:

3. **HTTP surface** — [`tests/test_sdk_contract.py`](../../tests/test_sdk_contract.py) reduces the FastAPI OpenAPI schema to just the endpoints this SDK calls and diffs it against [`sdk/contract/openapi-digest.json`](../contract/openapi-digest.json). A renamed or removed request field fails the build. Because `RunRequest` sets `extra="forbid"`, a field the SDK sends that the backend dropped is a hard 422 for users, not a silent no-op — so this test also pins that strictness.

4. **SSE surface** — OpenAPI cannot describe a stream, so [`sdk/contract/events.json`](../contract/events.json) stands in for it and both sides test against it. The Python test asserts the backend still *emits* the keys (reading the terminal frame's literal keys out of `execution/pipeline.py`, and running the real `_ser_synthesis` serializer). [`test/contract.test.ts`](test/contract.test.ts) asserts this SDK still *reads* them, driving the fixture stream through the real client over a real chunked SSE body.

Refresh the OpenAPI snapshot after an intentional API change:

```bash
UPDATE_SDK_CONTRACT=1 python -m pytest tests/test_sdk_contract.py
```

Update `sdk/contract/events.json` and both test suites together when an SSE frame changes shape. The contract file is a *floor*, not an inventory — the backend may emit more, and new event types arrive without a version bump.
