// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocked = vi.hoisted(() => {
  const openCursor = vi.fn();
  const index = { openCursor };
  const objectStore = { index: vi.fn(() => index) };
  const transaction = vi.fn(() => ({ objectStore: vi.fn(() => objectStore) }));
  const openDB = vi.fn(async () => ({ transaction }));
  const upperBound = vi.fn((value: unknown, open: boolean) => ({ kind: 'upperBound', value, open }));
  const lowerBound = vi.fn((value: unknown, open: boolean) => ({ kind: 'lowerBound', value, open }));
  return { openCursor, index, objectStore, transaction, openDB, upperBound, lowerBound };
});

vi.mock('idb', () => ({ openDB: mocked.openDB }));

Object.defineProperty(globalThis, 'IDBKeyRange', {
  configurable: true,
  value: { upperBound: mocked.upperBound, lowerBound: mocked.lowerBound },
});

import { loadConversationsPage } from './db';

describe('loadConversationsPage', () => {
  beforeEach(() => {
    mocked.openDB.mockClear();
    mocked.transaction.mockClear();
    mocked.objectStore.index.mockClear();
    mocked.openCursor.mockClear();
    mocked.upperBound.mockClear();
    mocked.lowerBound.mockClear();
  });

  it('uses an exclusive upper bound when paginating backwards', async () => {
    mocked.openCursor.mockResolvedValueOnce(null);

    await loadConversationsPage('cursor-123', 'prev');

    expect(mocked.upperBound).toHaveBeenCalledWith('cursor-123', true);
    expect(mocked.openCursor).toHaveBeenCalledWith(
      { kind: 'upperBound', value: 'cursor-123', open: true },
      'prev',
    );
  });

  it('uses an exclusive lower bound when paginating forwards', async () => {
    mocked.openCursor.mockResolvedValueOnce(null);

    await loadConversationsPage('cursor-456', 'next');

    expect(mocked.lowerBound).toHaveBeenCalledWith('cursor-456', true);
    expect(mocked.openCursor).toHaveBeenCalledWith(
      { kind: 'lowerBound', value: 'cursor-456', open: true },
      'next',
    );
  });

  it('does not end a page inside a run of equal timestamps', async () => {
    const PAGE = 50; // mirrors PAGE_SIZE in db.ts
    const rows = Array.from({ length: PAGE + 2 }, (_, n) => ({
      key: n < PAGE - 1 ? 1000 - n : 500, // last 3 rows tie on 500
      value: { id: `c${n}` },
    }));
    const at = (n: number): unknown =>
      n < rows.length ? { ...rows[n], continue: async () => at(n + 1) } : null;
    mocked.openCursor.mockResolvedValueOnce(at(0));

    const page = await loadConversationsPage();

    expect(page.items).toHaveLength(PAGE + 2);
    expect(page.nextCursor).toBe(500);
  });
});
