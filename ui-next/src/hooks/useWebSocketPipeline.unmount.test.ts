// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

/**
 * Tier F1, effect lifecycle. The unmount cleanup called `ws.close()` while
 * leaving `pipelineIdRef` set. `close()` fires `onclose` asynchronously, i.e.
 * after the cleanup has finished, and `onclose` reconnects whenever
 * `pipelineIdRef.current === pipelineId`. So the cleanup's own `clearReconnect()`
 * ran first and a fresh reconnect timer was scheduled straight after it, into a
 * ref nobody would ever clear again. That timer then reconnects an unmounted
 * hook and setStates on it, up to WS.maxReconnectAttempts times.
 *
 * `disconnect()` never had this bug: it nulls `pipelineIdRef` BEFORE `close()`,
 * so the `onclose` guard fails. The fix gives unmount the same ordering.
 *
 * A separate file from useWebSocketPipeline.test.ts on purpose: that file's
 * MockWebSocket has `close = vi.fn()` and never dispatches `onclose`, which is
 * exactly why the defect was invisible there. Changing that mock in place would
 * silently alter what its existing test means.
 */

const mocked = vi.hoisted(() => ({
  fetchWithCsrf: vi.fn(),
  getAuthToken: vi.fn(),
}));

vi.mock('@/lib/security-client', () => ({ fetchWithCsrf: mocked.fetchWithCsrf }));
vi.mock('@/lib/auth', () => ({ getAuthToken: mocked.getAuthToken }));

import { useWebSocketPipeline } from './useWebSocketPipeline';

/** Unlike the mock in the sibling file, this one dispatches `onclose` the way a
 *  real socket does — which is the entire mechanism under test. */
class ClosingMockWebSocket {
  static instances: ClosingMockWebSocket[] = [];
  url: string;
  readyState = 1;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    ClosingMockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = 3;
    // Asynchronous, as the real event is. A synchronous call here would run
    // inside the cleanup and mask the ordering bug entirely.
    setTimeout(() => this.onclose?.(), 0);
  }
}

function connectOk() {
  mocked.getAuthToken.mockResolvedValue(null);
  mocked.fetchWithCsrf.mockImplementation(async (url: string) => {
    if (url === '/api/health') return { ok: true };
    // The ticket route: doConnect destructures `ticket` off the JSON body.
    return { ok: true, json: async () => ({ ticket: 'tkt-1' }) };
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mocked.fetchWithCsrf.mockReset();
  mocked.getAuthToken.mockReset();
  ClosingMockWebSocket.instances = [];
  connectOk();
  vi.stubGlobal('WebSocket', ClosingMockWebSocket);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('useWebSocketPipeline unmount', () => {
  it('does not reconnect after the component unmounts', async () => {
    const { result, unmount } = renderHook(() => useWebSocketPipeline());

    await act(async () => {
      await result.current.connect('pipeline-1', vi.fn());
    });
    expect(ClosingMockWebSocket.instances).toHaveLength(1);

    unmount();

    // Let the asynchronous onclose land, then run any timer it scheduled.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    // Before the fix this was 2: onclose ran after the cleanup, saw
    // pipelineIdRef still set, and scheduled a reconnect nobody would cancel.
    expect(ClosingMockWebSocket.instances).toHaveLength(1);
  });

  it('makes no further network calls after unmount', async () => {
    const { result, unmount } = renderHook(() => useWebSocketPipeline());

    await act(async () => {
      await result.current.connect('pipeline-1', vi.fn());
    });
    const callsAtUnmount = mocked.fetchWithCsrf.mock.calls.length;

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    // A reconnect re-runs the health check and requests a fresh ticket, so the
    // count moving is the same defect seen from the network side.
    expect(mocked.fetchWithCsrf.mock.calls.length).toBe(callsAtUnmount);
  });

  it('still reconnects on an unexpected close while mounted', async () => {
    const { result } = renderHook(() => useWebSocketPipeline());

    await act(async () => {
      await result.current.connect('pipeline-1', vi.fn());
    });

    // The point of the fix is to stop reconnecting after unmount, not to stop
    // reconnecting. Without this, nulling the ref unconditionally would pass
    // both tests above while silently disabling recovery for live users.
    await act(async () => {
      ClosingMockWebSocket.instances[0].onclose?.();
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(ClosingMockWebSocket.instances.length).toBeGreaterThan(1);
  });

  it('does not reconnect after an explicit disconnect', async () => {
    const { result } = renderHook(() => useWebSocketPipeline());

    await act(async () => {
      await result.current.connect('pipeline-1', vi.fn());
    });

    act(() => {
      result.current.disconnect();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    // This path was always correct; pinned so the fix above and this stay in
    // agreement rather than drifting apart.
    expect(ClosingMockWebSocket.instances).toHaveLength(1);
  });
});
