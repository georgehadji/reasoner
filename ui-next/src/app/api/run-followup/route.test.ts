import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

/** Closing the tab must reach the backend: the proxy passes the client's abort signal upstream. */

vi.mock('@/lib/security-server', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/security-server')>();
  return {
    ...real,
    requireCsrfToken: vi.fn(async () => {}),
    getApiBaseUrl: () => 'http://backend:8000',
    validateUpstreamUrl: (url: string) => url,
    readJsonBody: vi.fn(async () => ({})),
    validateRunFollowupRequest: vi.fn((b: unknown) => b),
  };
});

import { POST } from './route';

afterEach(() => vi.unstubAllGlobals());

describe('POST /api/run-followup proxy', () => {
  it('forwards the request signal upstream', async () => {
    const upstream = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () => new Response('ok'));
    vi.stubGlobal('fetch', upstream);
    const req = new NextRequest('http://localhost/api/run-followup', { method: 'POST' });
    await POST(req);
    expect(upstream.mock.calls[0][1].signal).toBe(req.signal);
  });

  it('answers an aborted client quietly instead of logging a proxy error', async () => {
    const ctrl = new AbortController();
    const req = new NextRequest('http://localhost/api/run-followup', { method: 'POST', signal: ctrl.signal });
    vi.stubGlobal('fetch', vi.fn(async () => { ctrl.abort(); throw new DOMException('aborted', 'AbortError'); }));
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const resp = await POST(req);
    expect(resp.status).toBe(499);
    expect(err).not.toHaveBeenCalled();
    err.mockRestore();
  });
});
