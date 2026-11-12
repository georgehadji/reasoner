// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

/** SM-U2: docs/plans/implicit-state-machines-2026-11-11.md 1.3 */
const mocked = vi.hoisted(() => ({ fetchWithCsrf: vi.fn() }));
vi.mock('@/lib/security-client', () => ({ fetchWithCsrf: mocked.fetchWithCsrf }));

import { WS } from '@/lib/config';
import { useWebSocketPipeline } from './useWebSocketPipeline';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  readyState = 1;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: unknown = null;
  onerror: unknown = null;
  close = vi.fn();
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
}

const ok = (body: unknown = {}) => ({ ok: true, status: 200, json: async () => body });
const bad = (status: number) => ({ ok: false, status, json: async () => ({}) });

beforeEach(() => {
  vi.useFakeTimers();
  MockWebSocket.instances = [];
  mocked.fetchWithCsrf.mockReset();
  mocked.fetchWithCsrf.mockResolvedValue(ok({ ticket: 't' }));
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.spyOn(console, 'debug').mockImplementation(() => {});
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('SM-U2 websocket connection', () => {
  it('SM-U2: connected clears a stale lastError', async () => {
    mocked.fetchWithCsrf.mockResolvedValueOnce(bad(503));
    const { result } = renderHook(() => useWebSocketPipeline());
    await act(async () => {
      await result.current.connect('p1', vi.fn());
    });
    expect(result.current.status).toBe('error');
    expect(result.current.lastError).not.toBeNull();
    await act(async () => {
      await result.current.connect('p1', vi.fn());
    });
    act(() => MockWebSocket.instances[0].onopen?.());
    expect(result.current.status).toBe('connected');
    expect(result.current.lastError).toBeNull(); // bug: stale message kept after success
  });

  it('SM-U2: a ticket failure during a reconnect keeps retrying, then ends in error', async () => {
    const { result } = renderHook(() => useWebSocketPipeline());
    await act(async () => {
      await result.current.connect('p1', vi.fn());
    });
    act(() => MockWebSocket.instances[0].onopen?.());
    // From now on the health check passes but the ticket route fails.
    mocked.fetchWithCsrf.mockImplementation(async (url: string) => (url === '/api/health' ? ok() : bad(500)));
    act(() => MockWebSocket.instances[0].onclose?.());
    expect(result.current.status).toBe('reconnecting');
    for (let i = 0; i < WS.maxReconnectAttempts - 1; i++) {
      await act(async () => {
        await vi.runOnlyPendingTimersAsync();
      });
      expect(result.current.status).toBe('reconnecting'); // bug: terminal 'error' after the first failure
    }
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });
    expect(result.current.status).toBe('error'); // budget spent
  });

  it('SM-U2: overlapping connect() calls leave exactly one live socket', async () => {
    const { result } = renderHook(() => useWebSocketPipeline());
    await act(async () => {
      await Promise.all([result.current.connect('p1', vi.fn()), result.current.connect('p2', vi.fn())]);
    });
    expect(MockWebSocket.instances).toHaveLength(1); // bug: two sockets, the first leaked
    expect(MockWebSocket.instances[0].url).toContain('p2');
  });

  it('SM-U2: connect() over an open socket closes it and ignores its late onclose', async () => {
    const { result } = renderHook(() => useWebSocketPipeline());
    await act(async () => {
      await result.current.connect('p1', vi.fn());
    });
    const first = MockWebSocket.instances[0];
    act(() => first.onopen?.());
    await act(async () => {
      await result.current.connect('p2', vi.fn());
    });
    expect(first.close).toHaveBeenCalled();
    expect(first.onclose).toBeNull();
  });
});
