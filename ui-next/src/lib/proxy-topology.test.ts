import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

/**
 * OPS-9: with TRUSTED_PROXIES unset, a request through a CDN and a load
 * balancer keys its rate limit to the proxy, so every user shares a bucket.
 * Production now says so once and flags it for /api/health.
 */

const req = (xff: string) =>
  new NextRequest('http://localhost/api/run', { headers: { 'x-forwarded-for': xff } });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.resetModules();
});

describe('undeclared proxy chain', () => {
  it('warns once in production for a multi-hop header with no TRUSTED_PROXIES', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('TRUSTED_PROXIES', '');
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { getClientIp, proxyTopologyUndeclared } = await import('./security-server');

    getClientIp(req('203.0.113.9, 198.51.100.1, 10.0.0.2'));
    getClientIp(req('203.0.113.10, 198.51.100.1, 10.0.0.2'));

    expect(error).toHaveBeenCalledTimes(1);
    expect(error.mock.calls[0][0]).toContain('TRUSTED_PROXIES');
    expect(proxyTopologyUndeclared()).toBe(true);
  });

  it('stays quiet when the proxies are declared, or outside production', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('TRUSTED_PROXIES', '10.0.0.2');
    let mod = await import('./security-server');
    mod.getClientIp(req('203.0.113.9, 10.0.0.2'));
    expect(mod.proxyTopologyUndeclared()).toBe(false);

    vi.resetModules();
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('TRUSTED_PROXIES', '');
    mod = await import('./security-server');
    mod.getClientIp(req('203.0.113.9, 10.0.0.2'));
    expect(mod.proxyTopologyUndeclared()).toBe(false);
    expect(error).not.toHaveBeenCalled();
  });
});
