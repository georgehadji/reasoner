/**
 * Next proxy parity with the backend (OPS-8, dev and non-Caddy setups).
 *
 * - The rate-limit key trusted the leftmost X-Forwarded-For entry, which the
 *   client writes itself.
 * - The cookie-CSRF rule in proxy.ts 403'd every webhook and bearer-only
 *   agent call: neither ever carries the browser's cookie pair.
 * - neuro/sessions forwarded no Authorization, so the backend saw every
 *   caller as anonymous.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import { getClientIp } from './security-server';
import { csrfExempt } from '../proxy';

afterEach(() => {
  delete process.env.TRUSTED_PROXIES;
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('getClientIp', () => {
  const req = (xff: string) =>
    new NextRequest('http://localhost/api/run', { headers: { 'x-forwarded-for': xff } });

  it('ignores a client-supplied leftmost entry', () => {
    expect(getClientIp(req('6.6.6.6, 203.0.113.9'))).toBe('203.0.113.9');
  });

  it('skips trusted proxies from the right', () => {
    process.env.TRUSTED_PROXIES = '10.0.0.2, 10.0.0.3';
    expect(getClientIp(req('6.6.6.6, 203.0.113.9, 10.0.0.2, 10.0.0.3'))).toBe('203.0.113.9');
  });

  it('keeps a single hop', () => {
    expect(getClientIp(req('10.0.0.1'))).toBe('10.0.0.1');
  });

  // UI-11: X-Real-IP is client-writable wherever nothing in front overwrites it.
  it('ignores x-real-ip unless proxies are declared trusted', () => {
    const bare = new NextRequest('http://localhost/', { headers: { 'x-real-ip': '198.51.100.4' } });
    expect(getClientIp(bare)).toBe('unknown');
    process.env.TRUSTED_PROXIES = '10.0.0.2';
    expect(getClientIp(bare)).toBe('198.51.100.4');
  });
});

// UI-9: the client refreshed its CSRF token with GET /api/csrf. In production
// Caddy sends /api/* to FastAPI, which only has POST /api/csrf.
describe('csrf refresh verb', () => {
  it('the Next handler accepts POST like the backend', async () => {
    vi.stubEnv('CSRF_SECRET', 'x'.repeat(48));
    const route = await import('../app/api/csrf/route');
    expect(typeof route.POST).toBe('function');
    const res = await route.POST();
    expect(typeof (await res.json()).token).toBe('string');
  });

  it('no client code calls /api/csrf without POST', async () => {
    const { readdirSync, readFileSync, statSync } = await import('node:fs');
    const { join } = await import('node:path');
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(ts|tsx)$/.test(name) && !/\.test\./.test(name)) files.push(p);
      }
    };
    walk(join(__dirname, '..'));
    const offenders = files.filter((f) => /fetch\(\s*['"`]\/api\/csrf['"`]\s*\)/.test(readFileSync(f, 'utf8')));
    expect(offenders).toEqual([]);
  });
});

describe('csrfExempt', () => {
  const post = (path: string, headers: Record<string, string> = {}) =>
    new NextRequest(`http://localhost${path}`, { method: 'POST', headers });

  it('exempts provider webhooks', () => {
    expect(csrfExempt(post('/api/billing/webhook'))).toBe(true);
    expect(csrfExempt(post('/api/billing/paypal/webhook'))).toBe(true);
  });

  it('exempts agent routes only when they carry a bearer key', () => {
    expect(csrfExempt(post('/api/agent/run', { authorization: 'Bearer rsn_abc' }))).toBe(true);
    expect(csrfExempt(post('/api/agent/run'))).toBe(false);
  });

  it('does not exempt browser routes', () => {
    expect(csrfExempt(post('/api/run', { authorization: 'Bearer x' }))).toBe(false);
    expect(csrfExempt(post('/api/billing/checkout'))).toBe(false);
  });
});

describe('neuro/sessions proxy', () => {
  it('forwards Authorization to the backend', async () => {
    const fetchMock = vi.fn(async () => new Response('{"entries":[],"total":0}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const { GET } = await import('../app/api/neuro/sessions/route');

    await GET(
      new NextRequest('http://localhost/api/neuro/sessions?limit=5', {
        headers: { authorization: 'Bearer token-1', 'x-forwarded-for': '192.0.2.77' },
      }),
    );

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).authorization).toBe('Bearer token-1');
  });
});
