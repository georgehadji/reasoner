// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

const mocked = vi.hoisted(() => ({
  fetchWithCsrf: vi.fn(),
  getAuthToken: vi.fn(),
}));

vi.mock('@/lib/security-client', () => ({ fetchWithCsrf: mocked.fetchWithCsrf }));
vi.mock('@/lib/auth', () => ({ getAuthToken: mocked.getAuthToken }));

import { useWebSocketPipeline } from './useWebSocketPipeline';

describe('useWebSocketPipeline', () => {
  beforeEach(() => {
    mocked.fetchWithCsrf.mockReset();
    mocked.getAuthToken.mockReset();
    mocked.fetchWithCsrf.mockResolvedValue({ ok: true });
    mocked.getAuthToken.mockResolvedValue(null);
    class MockWebSocket {
      url: string;
      close = vi.fn();
      readyState = 1;

      constructor(url: string) {
        this.url = url;
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  it('checks the generic health route before opening a websocket connection', async () => {
    const { result } = renderHook(() => useWebSocketPipeline());

    await act(async () => {
      await result.current.connect('pipeline-1', vi.fn());
    });

    expect(mocked.fetchWithCsrf).toHaveBeenCalledWith('/api/health', expect.any(Object));
  });
});
