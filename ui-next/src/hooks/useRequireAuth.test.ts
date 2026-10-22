// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { act } from 'react';
import type { User } from '@supabase/supabase-js';

const replace = vi.fn();
// Stable identity, like Next's real router; a fresh object per render would
// re-run the effect.
const router = { replace };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/settings',
}));

import { useAppStore } from '@/stores/app-store';
import { useRequireAuth } from './useRequireAuth';

describe('useRequireAuth', () => {
  beforeEach(() => {
    replace.mockClear();
    useAppStore.setState({ user: null, isAuthenticated: false, isAuthLoading: true });
  });

  it('does not redirect while the session is still loading', () => {
    const { result } = renderHook(() => useRequireAuth());
    expect(result.current).toBe('loading');
    expect(replace).not.toHaveBeenCalled();
  });

  it('redirects once, with the return path, when anonymous', () => {
    const { rerender } = renderHook(() => useRequireAuth());
    act(() => useAppStore.getState().setAuthLoading(false));
    rerender();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith('/login?next=%2Fsettings');
  });

  it('never redirects an authenticated user', () => {
    useAppStore.getState().setUser({ id: 'u1' } as User);
    useAppStore.getState().setAuthLoading(false);
    const { result } = renderHook(() => useRequireAuth());
    expect(result.current).toBe('authenticated');
    expect(replace).not.toHaveBeenCalled();
  });
});
