import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

/** Closing the tab must reach the backend: the proxy passes the client's abort signal upstream. */

vi.mock('@/lib/security-server', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/security-server')>();
  return {
    ...real,
    extractBearerToken: vi.fn(() => 'key'),
    getApiBaseUrl: () => 'http://backend:8000',
    validateUpstreamUrl: (url: string) => url,
    readJsonBody: vi.fn(async () => ({})),
    validateRunRequest: vi.fn((b: unknown) => b),
  };
});

import { POST } from './route';

afterEach(() => vi.unstubAllGlobals());

describe('POST /api/agent/run proxy', () => {
  it('forwards the request signal upstream', async () => {
    const upstream = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () => new Response('ok'));
    vi.stubGlobal('fetch', upstream);
    const req = new NextRequest('http://localhost/api/agent/run', { method: 'POST' });
    await POST(req);
    expect(upstream.mock.calls[0][1].signal).toBe(req.signal);
  });

  it('answers an aborted client with 499 and no error log', async () => {
    const ctrl = new AbortController();
    const req = new NextRequest('http://localhost/api/agent/run', { method: 'POST', signal: ctrl.signal });
    vi.stubGlobal('fetch', vi.fn(async () => { ctrl.abort(); throw new DOMException('aborted', 'AbortError'); }));
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const resp = await POST(req);
    expect(resp.status).toBe(499);
    expect(err).not.toHaveBeenCalled();
    err.mockRestore();
  });
});
