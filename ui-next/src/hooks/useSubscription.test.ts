// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { User } from '@supabase/supabase-js';

vi.mock('@/lib/api-client', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api-client';
import { useAppStore } from '@/stores/app-store';
import { useSubscription } from './useSubscription';

/** UI-7: an anonymous visitor's 401 used to bounce public pages to /login. */
describe('useSubscription', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
    vi.mocked(apiFetch).mockResolvedValue(
      new Response(JSON.stringify({ tier: 'pro', status: 'active' }), { status: 200 }),
    );
    useAppStore.setState({
      user: null,
      isAuthenticated: false,
      isAuthLoading: false,
      subscription: null,
      subscriptionOwner: null,
    });
  });

  it('does not fetch for an anonymous visitor', () => {
    renderHook(() => useSubscription());
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('does not fetch while the session is loading', () => {
    useAppStore.setState({ isAuthLoading: true });
    renderHook(() => useSubscription());
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('fetches once a user is present', async () => {
    useAppStore.getState().setUser({ id: 'u1' } as User);
    renderHook(() => useSubscription());
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });

  it('re-fetches when a different user signs in', async () => {
    useAppStore.setState({
      user: { id: 'u2' } as User,
      isAuthenticated: true,
      subscription: { tier: 'enterprise', status: 'active' },
      subscriptionOwner: 'u1',
    });
    renderHook(() => useSubscription());
    await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  });
});
