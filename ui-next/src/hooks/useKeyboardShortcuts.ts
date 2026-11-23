'use client';

import { useEffect, useRef } from 'react';

export function useKeyboardShortcuts({
  onToggleSidebar,
  onShowShortcuts,
  onStop,
  onClearComposer,
  onFocusComposer,
  onCopyLastResponse,
  onCommandPalette,
}: {
  onToggleSidebar?: () => void;
  onShowShortcuts?: () => void;
  onStop?: () => void;
  onClearComposer?: () => void;
  onFocusComposer?: () => void;
  onCopyLastResponse?: () => void;
  onCommandPalette?: () => void;
}) {
  const callbacksRef = useRef({
    onToggleSidebar,
    onShowShortcuts,
    onStop,
    onClearComposer,
    onFocusComposer,
    onCopyLastResponse,
    onCommandPalette,
  });

  useEffect(() => {
    callbacksRef.current = {
      onToggleSidebar,
      onShowShortcuts,
      onStop,
      onClearComposer,
      onFocusComposer,
      onCopyLastResponse,
      onCommandPalette,
    };
  });

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const isTyping = target.closest('textarea, input');
      const cbs = callbacksRef.current;

      // Command palette: Ctrl/Cmd+K
      if ((e.ctrlKey || e.metaKey) && e.key === 'k' && !isTyping) {
        e.preventDefault();
        cbs.onCommandPalette?.();
        return;
      }

      // Focus composer: /
      if (e.key === '/' && !isTyping) {
        e.preventDefault();
        cbs.onFocusComposer?.();
        return;
      }

      // Clear composer: Ctrl/Cmd+L
      if ((e.ctrlKey || e.metaKey) && e.key === 'l' && !isTyping) {
        e.preventDefault();
        cbs.onClearComposer?.();
        return;
      }

      // Copy last response: Ctrl/Cmd+Shift+C
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'C' && !isTyping) {
        e.preventDefault();
        cbs.onCopyLastResponse?.();
        return;
      }

      if (e.key === '?' && !isTyping) {
        e.preventDefault();
        cbs.onShowShortcuts?.();
      }
      if (e.key === 'b' && !isTyping) {
        e.preventDefault();
        cbs.onToggleSidebar?.();
      }
      // Escape inside a dialog closes that dialog; it must not also kill the run.
      if (e.key === 'Escape' && !target.closest('dialog[open], [role="dialog"]')) {
        cbs.onStop?.();
      }
    }

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);
}
