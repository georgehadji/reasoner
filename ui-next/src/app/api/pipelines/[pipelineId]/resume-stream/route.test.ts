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
  };
});

import { POST } from './route';

const ctx = { params: Promise.resolve({ pipelineId: 'p1' }) };

afterEach(() => vi.unstubAllGlobals());

describe('POST /api/pipelines/[id]/resume-stream proxy', () => {
  it('forwards the request signal upstream', async () => {
    const upstream = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () => new Response('ok'));
    vi.stubGlobal('fetch', upstream);
    const req = new NextRequest('http://localhost/api/pipelines/p1/resume-stream', { method: 'POST' });
    await POST(req, ctx);
    expect(upstream.mock.calls[0][1].signal).toBe(req.signal);
  });

  it('answers an aborted client with 499 and no error log', async () => {
    const ctrl = new AbortController();
    const req = new NextRequest('http://localhost/api/pipelines/p1/resume-stream', {
      method: 'POST',
      signal: ctrl.signal,
    });
    vi.stubGlobal('fetch', vi.fn(async () => { ctrl.abort(); throw new DOMException('aborted', 'AbortError'); }));
    const err = vi.spyOn(console, 'error').mockImplementation(() => {});
    const resp = await POST(req, ctx);
    expect(resp.status).toBe(499);
    expect(err).not.toHaveBeenCalled();
    err.mockRestore();
  });
});
