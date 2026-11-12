// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

/** SM-U6: loadMore writes setHistory([...history, ...next]) from a stale closure. */
const db = vi.hoisted(() => ({
  loadConversationsPage: vi.fn(),
  deleteConversation: vi.fn(async () => {}),
}));
vi.mock('@/lib/db', () => ({
  loadConversationsPage: db.loadConversationsPage,
  saveConversation: vi.fn(),
  deleteConversation: db.deleteConversation,
  clearAllConversations: vi.fn(),
}));

import { useConversationHistory } from './useConversationHistory';
import { useAppStore } from '@/stores/app-store';

const c = (id: string) => ({ id }) as never;

beforeEach(() => {
  db.loadConversationsPage.mockReset();
  useAppStore.setState({ history: [], user: null });
});

describe('SM-U6 loadMore stale closure', () => {
  it('SM-U6: a row deleted while loadMore is in flight must not reappear', async () => {
    let resolveMore!: (v: unknown) => void;
    db.loadConversationsPage
      .mockResolvedValueOnce({ items: [c('A'), c('B'), c('C')], nextCursor: 'c1' }) // initial
      .mockImplementationOnce(() => new Promise((r) => { resolveMore = r; })) // loadMore, held
      .mockResolvedValueOnce({ items: [c('A'), c('C')], nextCursor: 'c1' }); // refresh after delete

    const { result } = renderHook(() => useConversationHistory());
    await waitFor(() => expect(useAppStore.getState().history).toHaveLength(3));

    let more!: Promise<void>;
    act(() => { more = result.current.loadMore(); }); // closure captures history=[A,B,C]
    await act(async () => { await result.current.remove('B'); });
    expect(useAppStore.getState().history.map((h) => h.id)).toEqual(['A', 'C']);

    await act(async () => { resolveMore({ items: [c('D')], nextCursor: null }); await more; });
    // bug: [A,B,C,D]
    expect(useAppStore.getState().history.map((h) => h.id)).not.toContain('B');
  });
});
