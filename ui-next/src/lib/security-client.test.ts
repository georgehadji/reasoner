// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '@supabase/supabase-js';

vi.mock('./auth', () => ({ getAuthToken: vi.fn(async () => null) }));
vi.mock('./error-reporting', () => ({ reportError: vi.fn(async () => {}) }));

import { useAppStore } from '@/stores/app-store';
import { fetchWithCsrf } from './security-client';

/**
 * UI-7. The transport used to navigate on every 401, which sent logged-out
 * visitors of public pages to /login and left callers hanging on a promise that
 * never resolved. A 401 is now just a response; the page decides.
 */
describe('fetchWithCsrf 401 handling', () => {
  beforeEach(() => {
    document.cookie = 'csrf_token=abc';
    useAppStore.setState({ user: { id: 'u1' } as User, isAuthenticated: true, isAuthLoading: false });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('returns the 401 to the caller and does not navigate', async () => {
    const hrefSet = vi.fn();
    const loc = { ...window.location } as Location;
    Object.defineProperty(loc, 'href', { set: hrefSet, get: () => 'http://localhost/' });
    vi.stubGlobal('location', loc);
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));

    const resp = await fetchWithCsrf('/api/anything');

    expect(resp.status).toBe(401);
    expect(hrefSet).not.toHaveBeenCalled();
  });

  it('marks the session expired so the page guard can redirect', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
    await fetchWithCsrf('/api/anything');
    expect(useAppStore.getState().user).toBeNull();
  });
});

/** UI-9. Caddy sends /api/* to FastAPI, which serves POST /api/csrf only. */
describe('fetchWithCsrf token refresh', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('refreshes the CSRF token with POST', async () => {
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    const fetchMock = vi.fn(async (url: string) =>
      url === '/api/csrf'
        ? new Response(JSON.stringify({ token: 'fresh' }), { status: 200 })
        : new Response('{}', { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchWithCsrf('/api/anything', { method: 'POST' });

    const call = fetchMock.mock.calls.find((c) => c[0] === '/api/csrf') as unknown as [string, RequestInit];
    expect(call[1]?.method).toBe('POST');
  });
});
