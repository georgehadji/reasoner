// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

/**
 * SM-U1 (docs/plans/implicit-state-machines-2026-11-11.md 1.3).
 * A page-level test of app/chat/page.tsx is not honest (huge), so this drives
 * the REAL useRunController + REAL app-store through a harness that mirrors the
 * page's submitRun/handleStop wiring (page.tsx:351, 971-977, 1010-1015):
 * setRunning(true) at start and a
 * `finally { if (!run.superseded(ticket)) { wsDisconnect(); setRunning(false); } }`.
 */
vi.mock('@/lib/api-client', () => ({ stopPipeline: vi.fn() }));

import { useRunController } from './useRunController';
import { useAppStore } from '@/stores/app-store';

const tick = () => new Promise((r) => setTimeout(r, 0));

function useHarness(wsDisconnect: () => void) {
  const run = useRunController(vi.fn());
  const setRunning = useAppStore((s) => s.setRunning);
  const submit = async (stream: (signal: AbortSignal) => Promise<void>) => {
    const ticket = run.begin();
    if (!ticket) return;
    try {
      setRunning(true);
      try {
        await stream(ticket.abort.signal);
      } finally {
        // page.tsx submitRun finally: a stale (superseded) run touches nothing.
        if (!run.superseded(ticket)) {
          wsDisconnect();
          setRunning(false);
        }
      }
    } finally {
      run.finish(ticket);
    }
  };
  const stop = () => {
    run.stop();
    setRunning(false);
  };
  return { submit, stop };
}

// Like streamEvents: resolves quietly (a bit later) once aborted.
const abortableStream = (signal: AbortSignal) =>
  new Promise<void>((res) => signal.addEventListener('abort', () => setTimeout(res, 5), { once: true }));
const hangingStream = () => new Promise<void>(() => {});

beforeEach(() => useAppStore.setState({ running: false }));

describe('SM-U1 stop then immediate resubmit', () => {
  it('SM-U1: old run finally must not clear running of the new run', async () => {
    const wsDisconnect = vi.fn();
    const { result } = renderHook(() => useHarness(wsDisconnect));
    void result.current.submit(abortableStream);
    await act(tick);
    act(() => result.current.stop());
    void result.current.submit(hangingStream);
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(useAppStore.getState().running).toBe(true); 
  });

  it('SM-U1: old run finally must not disconnect the WS of the new run', async () => {
    const wsDisconnect = vi.fn();
    const { result } = renderHook(() => useHarness(wsDisconnect));
    void result.current.submit(abortableStream);
    await act(tick);
    act(() => result.current.stop());
    void result.current.submit(hangingStream);
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(wsDisconnect).not.toHaveBeenCalled(); 
  });

  it('SM-U1 (holds): the controller allows a new ticket right after stop, and only one', () => {
    const { result } = renderHook(() => useRunController(vi.fn()));
    const t1 = result.current.begin();
    result.current.stop();
    const t2 = result.current.begin();
    expect(t2).not.toBeNull();
    expect(t2).not.toBe(t1);
    expect(result.current.begin()).toBeNull();
  });
});
