'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAppStore } from '@/stores/app-store';
import {
  loadConversationsPage,
  saveConversation as dbSaveConversation,
  deleteConversation as dbDeleteConversation,
  clearAllConversations as dbClearAllConversations,
  ConversationPage,
} from '@/lib/db';
import { Conversation } from '@/lib/types';

export function useConversationHistory() {
  const history = useAppStore((s) => s.history);
  const setHistory = useAppStore((s) => s.setHistory);
  // History is per user (lib/db.ts). Reload when the user changes, or the
  // previous user's list stays on screen after sign-out (UI-5).
  const userId = useAppStore((s) => s.user?.id ?? null);

  const [page, setPage] = useState<ConversationPage | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let mounted = true;
    loadConversationsPage()
      .then((firstPage) => {
        if (!mounted) return;
        setPage(firstPage);
        setHistory(firstPage.items);
      })
      .catch((err) => {
        if (mounted) console.error(err);
      });
    return () => { mounted = false; };
  }, [setHistory, userId]);

  const loadMore = useCallback(async () => {
    if (!page?.nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await loadConversationsPage(page.nextCursor);
      setPage((prev) =>
        prev ? { items: [...prev.items, ...next.items], nextCursor: next.nextCursor } : next,
      );
      setHistory([...history, ...next.items]);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingMore(false);
    }
  }, [page, loadingMore, setHistory, history]);

  const refresh = async () => {
    const firstPage = await loadConversationsPage();
    setPage(firstPage);
    setHistory(firstPage.items);
  };

  const save = async (conversation: Conversation) => {
    await dbSaveConversation(conversation);
    await refresh();
  };

  const remove = async (id: string) => {
    await dbDeleteConversation(id);
    await refresh();
  };

  const clear = async () => {
    await dbClearAllConversations();
    await refresh();
  };

  return { history, page, loadingMore, loadMore, refresh, save, remove, clear };
}
