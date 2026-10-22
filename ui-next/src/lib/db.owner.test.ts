import { describe, expect, it, vi } from 'vitest';

/**
 * UI-5: IndexedDB history was one database for every user of the browser, so
 * after A signed out, B signed in and saw A's conversations. History now
 * lives in one database per user. The fake keeps one store per database
 * name, which is the property under test.
 */

const dbs = vi.hoisted(() => new Map<string, Map<string, unknown>>());

vi.mock('idb', () => ({
  openDB: vi.fn(async (name: string) => {
    if (!dbs.has(name)) dbs.set(name, new Map());
    const rows = dbs.get(name)!;
    return {
      put: vi.fn(async (_store: string, value: { id: string }) => {
        rows.set(value.id, value);
      }),
      getAll: vi.fn(async () => [...rows.values()]),
    };
  }),
  deleteDB: vi.fn(async (name: string) => {
    dbs.delete(name);
  }),
}));

import { clearLegacyHistory, deleteHistory, loadAllConversations, saveConversation, setHistoryOwner } from './db';
import type { Conversation } from './types';

const conversation = { id: 'c1', problem: 'p', phases: [], errors: [] } as unknown as Conversation;

describe('per-user history', () => {
  it("B does not see A's conversations after A signs out", async () => {
    setHistoryOwner('user-a');
    await saveConversation(conversation);
    expect(await loadAllConversations()).toHaveLength(1);

    setHistoryOwner(null); // A signs out
    expect(await loadAllConversations()).toEqual([]);
    setHistoryOwner('user-b');
    expect(await loadAllConversations()).toEqual([]);

    setHistoryOwner('user-a');
    expect(await loadAllConversations()).toHaveLength(1);
  });

  it("deleting an account's history removes only that user's database", async () => {
    setHistoryOwner('user-c');
    await saveConversation(conversation);
    await deleteHistory('user-c');
    expect(await loadAllConversations()).toEqual([]);
    setHistoryOwner('user-a');
    expect(await loadAllConversations()).toHaveLength(1);
  });

  it('clears the old shared database rather than migrating it (Q9)', async () => {
    dbs.set('ARA_Pipeline_v2', new Map([['old', {}]]));
    await clearLegacyHistory();
    expect(dbs.has('ARA_Pipeline_v2')).toBe(false);
  });
});
