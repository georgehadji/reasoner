import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/security-server', () => ({
  getApiBaseUrl: () => 'http://backend:8000',
  validateUpstreamUrl: (url: string) => url,
  proxyTopologyUndeclared: () => false,
}));

import { GET } from './route';

afterEach(() => vi.unstubAllGlobals());

describe('GET /api/health', () => {
  it('asks the backend health endpoint, not its root', async () => {
    const fetchMock = vi.fn(async () => new Response('{"status":"healthy","checks":{}}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const resp = await GET();

    expect(fetchMock).toHaveBeenCalledWith('http://backend:8000/api/health', expect.any(Object));
    expect(await resp.json()).toEqual({ status: 'healthy', checks: {} });
  });

  it('answers 503 unhealthy when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('ECONNREFUSED'); }));

    const resp = await GET();

    expect(resp.status).toBe(503);
    expect(await resp.json()).toEqual({ status: 'unhealthy', error: 'Backend unreachable' });
  });
});
