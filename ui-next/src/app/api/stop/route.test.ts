import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

/**
 * UI-4: the stop proxy forwarded a bare POST /api/stop. Upstream that is the
 * admin "stop every user's run": a 403 the UI swallowed for a normal user,
 * every user's runs cancelled for an admin. It now forwards one run_id and
 * refuses a request without one.
 */

vi.mock('@/lib/security-server', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/security-server')>();
  return {
    ...real,
    requireCsrfToken: vi.fn(async () => {}),
    getApiBaseUrl: () => 'http://backend:8000',
    validateUpstreamUrl: (url: string) => url,
  };
});

import { POST } from './route';

afterEach(() => vi.unstubAllGlobals());

describe('POST /api/stop proxy', () => {
  it('forwards the run_id upstream', async () => {
    const upstream = vi.fn<(url: string) => Promise<Response>>(async () => new Response('{"status":"stopped"}'));
    vi.stubGlobal('fetch', upstream);
    const resp = await POST(new NextRequest('http://localhost/api/stop?run_id=run-1', { method: 'POST' }));
    expect(resp.status).toBe(200);
    expect(upstream.mock.calls[0][0]).toBe('http://backend:8000/api/stop?run_id=run-1');
  });

  it('refuses a bare stop instead of forwarding the global one', async () => {
    const upstream = vi.fn();
    vi.stubGlobal('fetch', upstream);
    const resp = await POST(new NextRequest('http://localhost/api/stop', { method: 'POST' }));
    expect(resp.status).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });
});
