// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// Must mock before importing the hook
vi.mock('@/lib/api-client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api-client';
import { useQuota } from './useQuota';

describe('useQuota', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not produce unhandled rejection when quota fetch fails (BUG-006 regression)', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'));
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    renderHook(() => useQuota());

    // Allow microtasks to run
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));

    // No console.error should have been logged for the unhandled rejection
    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });

  it('sets quota state when fetch succeeds', async () => {
    const mockQuota = { used: 10, max: 100, remaining: 90, reset_date: '2026-05-01' };
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockQuota),
    });

    const { result } = renderHook(() => useQuota());

    await waitFor(() => expect(result.current.quota).toEqual(mockQuota));
    expect(result.current.loading).toBe(false);
  });

  it('passes the unlimited signal through (max null, never a numeric cap)', async () => {
    const mockQuota = { used: 0, max: null, unlimited: true, remaining: -1, reset_date: '2026-11-01' };
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockQuota),
    });

    const { result } = renderHook(() => useQuota());

    await waitFor(() => expect(result.current.quota).toEqual(mockQuota));
    expect(result.current.quota?.unlimited).toBe(true);
    expect(result.current.quota?.max).toBeNull();
  });
});
