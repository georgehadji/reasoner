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
});
