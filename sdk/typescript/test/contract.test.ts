/**
 * The SDK half of the SSE contract.
 *
 * `sdk/contract/events.json` is the shared source of truth. `tests/test_sdk_contract.py`
 * asserts the backend still *emits* these keys; this file asserts the SDK still
 * *reads* them, driving the fixture stream through the real client over a real
 * SSE body rather than testing `summarise()` in isolation.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, test } from 'vitest';
import { ReasonerClient } from '../src/client.js';
import { isEvent, type ReasonerEvent } from '../src/events.js';

interface EventsContract {
  version: number;
  required_frames: Record<string, { required_keys: string[]; container?: string }>;
  action_step_keys: string[];
  sample_stream: Record<string, unknown>[];
  expected_summary: Record<string, unknown>;
}

const CONTRACT: EventsContract = JSON.parse(
  readFileSync(fileURLToPath(new URL('../../contract/events.json', import.meta.url)), 'utf-8'),
);

/** Serve the fixture stream as a real SSE body, chunked at an awkward stride. */
function fixtureClient(stride = 13): ReasonerClient {
  const body = CONTRACT.sample_stream.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
  const bytes = new TextEncoder().encode(body);

  return new ReasonerClient({
    apiKey: 'rsn_live_contract',
    baseUrl: 'https://example.test',
    fetch: async () =>
      new Response(
        new ReadableStream({
          start(controller) {
            for (let i = 0; i < bytes.length; i += stride) {
              controller.enqueue(bytes.slice(i, i + stride));
            }
            controller.close();
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
      ),
  });
}

describe('SSE contract', () => {
  test('the contract file is the version this SDK was written against', () => {
    expect(CONTRACT.version).toBe(1);
  });

  test('runToCompletion extracts exactly what the contract promises', async () => {
    const result = await fixtureClient().runToCompletion({ problem: 'contract' });
    const expected = CONTRACT.expected_summary;

    expect(result.synthesis).toBe(expected.synthesis);
    expect(result.criticalInsights).toEqual(expected.criticalInsights);
    expect(result.openQuestions).toEqual(expected.openQuestions);
    expect(result.claimLabels).toEqual(expected.claimLabels);
    expect(result.costUsd).toBeCloseTo(expected.costUsd as number);
    expect(result.tokens).toEqual(expected.tokens);
    expect(result.durationSeconds).toBeCloseTo(expected.durationSeconds as number);
    expect(result.modelsUsed).toEqual(expected.modelsUsed);
    expect(result.preset).toBe(expected.preset);
    expect(result.method).toBe(expected.method);
    expect(result.errors).toEqual(expected.errors);
  });

  test('claim labels stay a mapping, not an array', async () => {
    const result = await fixtureClient().runToCompletion({ problem: 'contract' });

    expect(Array.isArray(result.claimLabels)).toBe(false);
    expect(Object.values(result.claimLabels).every((v) => typeof v === 'string')).toBe(true);
    expect(Object.keys(result.claimLabels).length).toBeGreaterThan(0);
  });

  test('every action step carries the five fields the contract declares', async () => {
    const result = await fixtureClient().runToCompletion({ problem: 'contract' });

    expect(result.actionBlueprint.length).toBeGreaterThan(0);
    for (const step of result.actionBlueprint) {
      expect(Object.keys(step).sort()).toEqual([...CONTRACT.action_step_keys].sort());
      expect(Object.values(step).every((v) => typeof v === 'string')).toBe(true);
    }
  });

  test('the done frame is read for every key the contract requires', async () => {
    const events: ReasonerEvent[] = [];
    for await (const event of fixtureClient().run({ problem: 'contract' })) events.push(event);

    const done = events.find((e) => isEvent(e, 'done'));
    expect(done).toBeDefined();

    for (const key of CONTRACT.required_frames.done!.required_keys) {
      expect(done).toHaveProperty(key);
    }
  });

  test('an event type postdating this SDK survives the round trip', async () => {
    const events: ReasonerEvent[] = [];
    for await (const event of fixtureClient().run({ problem: 'contract' })) events.push(event);

    const unknown = events.find((e) => e.type === 'an_event_added_after_this_contract_was_written');
    expect(unknown).toBeDefined();
    expect(unknown!.payload).toBe('must be ignored, not fatal');

    // And it must not have polluted the summary.
    const result = await fixtureClient().runToCompletion({ problem: 'contract' });
    expect(result.synthesis).toBe(CONTRACT.expected_summary.synthesis);
  });

  test('a crashed run yields a reduced done frame without throwing', async () => {
    // The backend emits `{type: 'done', errors: [...]}` on a pipeline exception.
    const body = 'data: {"type":"done","errors":["Pipeline processing error: TimeoutError"]}\n\n';
    const client = new ReasonerClient({
      apiKey: 'k',
      baseUrl: 'https://example.test',
      fetch: async () =>
        new Response(body, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
    });

    const result = await client.runToCompletion({ problem: 'contract' });

    expect(result.synthesis).toBe('');
    expect(result.costUsd).toBe(0);
    expect(result.tokens).toEqual({ input: 0, output: 0, total: 0 });
    expect(result.errors).toEqual(['Pipeline processing error: TimeoutError']);
  });
});
