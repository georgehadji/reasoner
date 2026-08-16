import { describe, expect, test, vi } from 'vitest';
import { fromRunResult, ReasonerClient, summarise } from '../src/client.js';
import { DuplicateRunError, InsufficientCreditsError, RateLimitError } from '../src/errors.js';
import { isEvent, type ReasonerEvent } from '../src/events.js';

/** An SSE response body built from event objects. */
function sseResponse(events: object[], init: ResponseInit = {}): Response {
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
    ...init,
  });
}

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

/** A client wired to a scripted fetch, plus the recorded calls. */
function clientWith(...responses: (Response | (() => Response))[]) {
  const calls: { url: string; init: RequestInit; body: Record<string, unknown> }[] = [];
  let index = 0;

  const fetchImpl = vi.fn(async (url: string | URL | Request, init: RequestInit = {}) => {
    const raw = typeof init.body === 'string' ? init.body : '{}';
    calls.push({ url: String(url), init, body: JSON.parse(raw) });
    const next = responses[Math.min(index++, responses.length - 1)];
    return typeof next === 'function' ? next() : next!;
  }) as unknown as typeof globalThis.fetch;

  const client = new ReasonerClient({
    apiKey: 'rsn_live_test',
    baseUrl: 'https://example.test',
    fetch: fetchImpl,
  });

  return { client, calls };
}

async function drain(iterable: AsyncIterable<ReasonerEvent>): Promise<ReasonerEvent[]> {
  const out: ReasonerEvent[] = [];
  for await (const event of iterable) out.push(event);
  return out;
}

describe('run', () => {
  test('streams events in order', async () => {
    const { client } = clientWith(
      sseResponse([
        { type: 'start', preset: 'auto-budget' },
        { type: 'phase_complete', phase: 2, name: 'Perspectives' },
        { type: 'done', total_cost_usd: 0.019 },
      ]),
    );

    const events = await drain(client.run({ problem: 'test' }));
    expect(events.map((e) => e.type)).toEqual(['start', 'phase_complete', 'done']);
  });

  test('sends the API key as a bearer token', async () => {
    const { client, calls } = clientWith(sseResponse([{ type: 'done' }]));
    await drain(client.run({ problem: 'test' }));

    const headers = new Headers(calls[0]!.init.headers);
    expect(headers.get('Authorization')).toBe('Bearer rsn_live_test');
    expect(headers.get('Accept')).toBe('text/event-stream');
  });

  test('generates a client_run_id when none is given', async () => {
    const { client, calls } = clientWith(sseResponse([{ type: 'done' }]));
    await drain(client.run({ problem: 'test' }));

    expect(calls[0]!.body.client_run_id).toEqual(expect.any(String));
    expect(String(calls[0]!.body.client_run_id).length).toBeGreaterThan(8);
  });

  test('honours a caller-supplied client_run_id', async () => {
    const { client, calls } = clientWith(sseResponse([{ type: 'done' }]));
    await drain(client.run({ problem: 'test', client_run_id: 'mine-1' }));

    expect(calls[0]!.body.client_run_id).toBe('mine-1');
  });

  test('omits unset options so the server applies its own defaults', async () => {
    const { client, calls } = clientWith(sseResponse([{ type: 'done' }]));
    await drain(client.run({ problem: 'test' }));

    expect(Object.keys(calls[0]!.body).sort()).toEqual(['client_run_id', 'problem']);
  });

  test('reuses the same client_run_id when retrying, so a retry cannot double-charge', async () => {
    const { client, calls } = clientWith(
      () => jsonResponse({ detail: 'slow down' }, 429, { 'Retry-After': '0' }),
      () => sseResponse([{ type: 'done' }]),
    );

    await drain(client.run({ problem: 'test' }));

    expect(calls).toHaveLength(2);
    expect(calls[0]!.body.client_run_id).toBe(calls[1]!.body.client_run_id);
  });

  test('gives up after maxRetries and raises the rate-limit error', async () => {
    const calls: string[] = [];
    const fetchImpl = vi.fn(async () => {
      calls.push('attempt');
      return jsonResponse({ detail: { error: 'Rate limit exceeded' } }, 429, {
        'Retry-After': '0',
      });
    }) as unknown as typeof globalThis.fetch;

    const client = new ReasonerClient({
      apiKey: 'k',
      baseUrl: 'https://example.test',
      fetch: fetchImpl,
      maxRetries: 1,
    });

    await expect(drain(client.run({ problem: 'test' }))).rejects.toBeInstanceOf(RateLimitError);
    expect(calls).toHaveLength(2);
  });

  test('does not retry a 402 — the balance will not refill on its own', async () => {
    const { client, calls } = clientWith(
      jsonResponse({ detail: 'Credit balance exhausted' }, 402),
    );

    await expect(drain(client.run({ problem: 'test' }))).rejects.toBeInstanceOf(
      InsufficientCreditsError,
    );
    expect(calls).toHaveLength(1);
  });

  test('does not retry a 409 — the original run is still in flight', async () => {
    const { client, calls } = clientWith(
      jsonResponse({ detail: 'Run mine-1 is already in progress' }, 409),
    );

    await expect(
      drain(client.run({ problem: 'test', client_run_id: 'mine-1' })),
    ).rejects.toBeInstanceOf(DuplicateRunError);
    expect(calls).toHaveLength(1);
  });

  test('aborts the request when the caller stops iterating', async () => {
    let signal: AbortSignal | undefined;
    const fetchImpl = vi.fn(async (_url: unknown, init: RequestInit = {}) => {
      signal = init.signal ?? undefined;
      return sseResponse([{ type: 'start' }, { type: 'phase_start' }, { type: 'done' }]);
    }) as unknown as typeof globalThis.fetch;

    const client = new ReasonerClient({
      apiKey: 'k',
      baseUrl: 'https://example.test',
      fetch: fetchImpl,
    });

    for await (const event of client.run({ problem: 'test' })) {
      if (event.type === 'start') break;
    }

    expect(signal?.aborted).toBe(true);
  });

  test('yields event types the SDK does not model', async () => {
    const { client } = clientWith(sseResponse([{ type: 'invented_later', detail: 'x' }]));
    const events = await drain(client.run({ problem: 'test' }));

    expect(events[0]!.type).toBe('invented_later');
    expect(isEvent(events[0]!, 'done')).toBe(false);
  });
});

describe('runToCompletion', () => {
  test('extracts the synthesis and cost', async () => {
    const { client } = clientWith(
      sseResponse([
        { type: 'start', preset: 'debate-premium' },
        { type: 'method_selected', method: 'debate' },
        {
          type: 'phase_complete',
          phase: 5,
          name: 'Synthesis',
          models: ['claude-sonnet', 'deepseek-v3'],
          data: {
            core_solution: 'Migrate incrementally.',
            critical_insights: ['The monolith is not the bottleneck.'],
            action_blueprint: [{ step: 'Extract billing first' }],
            open_questions: ['What is the deploy cadence?'],
            claim_labels: [{ claim: 'x', label: 'VERIFIED' }],
          },
        },
        {
          type: 'done',
          total_cost_usd: 0.0191,
          total_tokens: { input: 8213, output: 3944, total: 12157 },
          duration: 41.2,
          errors: [],
        },
      ]),
    );

    const result = await client.runToCompletion({ problem: 'test' });

    expect(result.synthesis).toBe('Migrate incrementally.');
    expect(result.criticalInsights).toEqual(['The monolith is not the bottleneck.']);
    expect(result.openQuestions).toEqual(['What is the deploy cadence?']);
    expect(result.actionBlueprint).toHaveLength(1);
    expect(result.costUsd).toBeCloseTo(0.0191);
    expect(result.tokens.total).toBe(12157);
    expect(result.durationSeconds).toBeCloseTo(41.2);
    expect(result.modelsUsed).toEqual(['claude-sonnet', 'deepseek-v3']);
    expect(result.preset).toBe('debate-premium');
    expect(result.method).toBe('debate');
    expect(result.events).toHaveLength(4);
  });
});

describe('runSync', () => {
  test('posts to the agent sync endpoint and returns a RunSummary', async () => {
    const { client, calls } = clientWith(
      jsonResponse({
        preset: 'debate-premium',
        method: 'debate',
        errors: [],
        total_tokens: { input: 8213, output: 3944, total: 12157 },
        total_cost_usd: 0.0191,
        duration_seconds: 41.2,
        synthesis: 'Migrate incrementally.',
        critical_insights: ['The monolith is not the bottleneck.'],
        open_questions: ['What is the deploy cadence?'],
        claim_labels: { x: 'VERIFIED' },
        action_blueprint: [{ step: '1', action: 'Extract billing', time_horizon: 'Q1', go_criteria: 'x', fallback: 'y' }],
        citations: [],
        models_used: ['claude-sonnet', 'deepseek-v3'],
      }),
    );

    const result = await client.runSync({ problem: 'test' });

    expect(calls[0]!.url).toBe('https://example.test/api/agent/run/sync');
    expect(result.synthesis).toBe('Migrate incrementally.');
    expect(result.criticalInsights).toEqual(['The monolith is not the bottleneck.']);
    expect(result.costUsd).toBeCloseTo(0.0191);
    expect(result.tokens.total).toBe(12157);
    expect(result.modelsUsed).toEqual(['claude-sonnet', 'deepseek-v3']);
    expect(result.method).toBe('debate');
    // No stream was ever read, so there is nothing to keep.
    expect(result.events).toEqual([]);
    expect(result.phaseCosts).toEqual({});
  });

  test('sends a client_run_id and does not retry a 409', async () => {
    const { client, calls } = clientWith(
      jsonResponse({ detail: 'Run mine-1 is already in progress' }, 409),
    );

    await expect(
      client.runSync({ problem: 'test', client_run_id: 'mine-1' }),
    ).rejects.toBeInstanceOf(DuplicateRunError);
    expect(calls).toHaveLength(1);
    expect(calls[0]!.body.client_run_id).toBe('mine-1');
  });
});

describe('fromRunResult', () => {
  test('maps a crashed run (empty synthesis, populated errors) without throwing', () => {
    const result = fromRunResult(
      {
        preset: 'auto-budget',
        method: null,
        errors: ['Pipeline processing error: TimeoutError'],
        total_tokens: { input: 0, output: 0, total: 0 },
        total_cost_usd: 0,
        duration_seconds: 0,
        synthesis: '',
        critical_insights: [],
        open_questions: [],
        claim_labels: {},
        action_blueprint: [],
        citations: [],
        models_used: [],
      },
      'run-1',
    );

    expect(result.synthesis).toBe('');
    expect(result.errors).toEqual(['Pipeline processing error: TimeoutError']);
    expect(result.method).toBeUndefined();
    expect(result.clientRunId).toBe('run-1');
  });
});

describe('summarise', () => {
  test('prefers the last phase that produced a solution', () => {
    const result = summarise(
      [
        { type: 'phase_complete', phase: 2, data: { core_solution: 'draft' } },
        { type: 'phase_complete', phase: 5, data: { core_solution: 'final' } },
      ] as ReasonerEvent[],
      'run-1',
    );

    expect(result.synthesis).toBe('final');
  });

  test('returns empty values when the run crashed before synthesising', () => {
    const result = summarise(
      [{ type: 'done', errors: ['Pipeline processing error: TimeoutError'] }] as ReasonerEvent[],
      'run-1',
    );

    expect(result.synthesis).toBe('');
    expect(result.costUsd).toBe(0);
    expect(result.tokens).toEqual({ input: 0, output: 0, total: 0 });
    expect(result.errors).toEqual(['Pipeline processing error: TimeoutError']);
  });

  test('merges mid-stream errors with the terminal error list, without duplicates', () => {
    const result = summarise(
      [
        { type: 'error', error: 'provider timeout' },
        { type: 'error', message: 'fallback used' },
        { type: 'done', errors: ['provider timeout'] },
      ] as ReasonerEvent[],
      'run-1',
    );

    expect(result.errors).toEqual(['provider timeout', 'fallback used']);
  });

  test('deduplicates models seen across phases, preserving first-seen order', () => {
    const result = summarise(
      [
        { type: 'phase_complete', phase: 2, models: ['a', 'b'] },
        { type: 'phase_complete', phase: 3, models: ['b', 'c'] },
      ] as ReasonerEvent[],
      'run-1',
    );

    expect(result.modelsUsed).toEqual(['a', 'b', 'c']);
  });

  test('falls back to the auto-selected method from the start event', () => {
    const result = summarise(
      [{ type: 'start', auto_selected_method: 'jury' }] as ReasonerEvent[],
      'run-1',
    );

    expect(result.method).toBe('jury');
  });
});

describe('json endpoints', () => {
  test('gate returns the routing decision', async () => {
    const { client, calls } = clientWith(
      jsonResponse({
        action: 'pipeline',
        method: 'debate',
        preset: 'debate-budget',
        confidence: 0.82,
        reasoning: 'Two defensible positions.',
        complexity: 'moderate',
        alternatives: [],
        needs_confirmation: false,
      }),
    );

    const decision = await client.gate({ problem: 'test' });

    expect(decision.preset).toBe('debate-budget');
    expect(calls[0]!.url).toBe('https://example.test/api/gate');
  });

  test('creditLedger builds its query string', async () => {
    const { client, calls } = clientWith(jsonResponse({ entries: [], limit: 10, offset: 20 }));
    await client.creditLedger({ limit: 10, offset: 20 });

    expect(calls[0]!.url).toBe('https://example.test/api/credits/ledger?limit=10&offset=20');
  });

  test('creditLedger omits the query string when unpaged', async () => {
    const { client, calls } = clientWith(jsonResponse({ entries: [], limit: 50, offset: 0 }));
    await client.creditLedger();

    expect(calls[0]!.url).toBe('https://example.test/api/credits/ledger');
  });

  test('strips a trailing slash from baseUrl', async () => {
    const fetchImpl = vi.fn(async (url: string | URL | Request) => {
      expect(String(url)).toBe('https://example.test/api/presets');
      return jsonResponse({ presets: {} });
    }) as unknown as typeof globalThis.fetch;

    const client = new ReasonerClient({
      apiKey: 'k',
      baseUrl: 'https://example.test/',
      fetch: fetchImpl,
    });
    await client.presets();
  });
});
