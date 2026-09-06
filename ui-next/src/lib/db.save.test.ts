import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Tier F1, persistence. `saveConversation` builds its record as an explicit
 * field-by-field literal rather than a spread. Two fields declared on
 * `Conversation` were simply not in that list, so they were dropped on every
 * save with no type error, because a literal that omits an optional field is
 * still a valid `Conversation`.
 *
 * `pipeline_id` is the load-bearing one. `chat/page.tsx:843` sets it on a
 * finished run, and `Sidebar.tsx:435` gates the Resume button on
 * `conv.pipeline_id && conv.kind === 'pipeline'`, reading a conversation back
 * out of IndexedDB. Written, dropped, then required by the reader: the Resume
 * button could never appear for a persisted run, so resume-after-reload was
 * dead for every user.
 *
 * The existing `db.test.ts` covers only cursor key-range direction, and mocks
 * `openCursor` to resolve null so its loop body never runs. Nothing tested
 * `saveConversation` at all.
 */

const put = vi.fn();

vi.mock('idb', () => ({
  openDB: vi.fn(async () => ({
    put,
    get: vi.fn(),
    getAll: vi.fn(),
    delete: vi.fn(),
    clear: vi.fn(),
    transaction: vi.fn(),
  })),
}));

import { saveConversation } from './db';
import type { Conversation } from './types';

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'c1',
    conversation_id: 'c1',
    turn_number: 1,
    timestamp: '2026-09-03T00:00:00.000Z',
    problem: 'p',
    phases: [],
    errors: [],
    preset: 'auto-budget',
    method: 'multi-perspective',
    total_tokens: null,
    kind: 'pipeline',
    ...overrides,
  };
}

/** The record actually handed to IndexedDB, which is what survives a reload. */
function storedRecord(): Conversation {
  return put.mock.calls[0][1] as Conversation;
}

beforeEach(() => {
  put.mockReset();
});

describe('saveConversation field fidelity', () => {
  it('persists pipeline_id, which the Resume button requires', async () => {
    await saveConversation(conversation({ pipeline_id: 'run-abc' }));

    expect(storedRecord().pipeline_id).toBe('run-abc');
  });

  it('persists widgets', async () => {
    const widgets = [{ type: 'chart', id: 'w1' }] as unknown as Conversation['widgets'];

    await saveConversation(conversation({ widgets }));

    expect(storedRecord().widgets).toEqual(widgets);
  });

  it('leaves both undefined when the caller omitted them', async () => {
    await saveConversation(conversation());

    const record = storedRecord();
    expect(record.pipeline_id).toBeUndefined();
    expect(record.widgets).toBeUndefined();
  });

  it('still applies its defaults to the required fields', async () => {
    // No-regression guard on the reason the literal is hand-written at all:
    // it exists to default these, so a future switch to a spread has to keep
    // doing so.
    await saveConversation(
      conversation({ errors: undefined as unknown as string[], preset: '', method: '' }),
    );

    const record = storedRecord();
    expect(record.errors).toEqual([]);
    expect(record.preset).toBe('unknown');
    expect(record.method).toBe('multi-perspective');
  });

  it('round-trips every declared optional field the caller sets', async () => {
    // The defect class is "a declared field missing from the literal", so the
    // durable test is the whole optional surface, not the two that were broken.
    await saveConversation(
      conversation({
        duration: 12.5,
        response_content: 'md',
        images: [{ data: 'd', model: 'm' }],
        prompt_meta: { original: 'o', enhanced: 'e' },
        pipeline_id: 'run-xyz',
      }),
    );

    const record = storedRecord();
    expect(record.duration).toBe(12.5);
    expect(record.response_content).toBe('md');
    expect(record.images).toEqual([{ data: 'd', model: 'm' }]);
    expect(record.prompt_meta).toEqual({ original: 'o', enhanced: 'e' });
    expect(record.pipeline_id).toBe('run-xyz');
  });
});
