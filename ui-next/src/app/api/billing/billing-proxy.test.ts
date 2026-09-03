import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Tier F1. The billing routes were the only mutating proxies with no
 * `rateLimit` call. Each POST creates a checkout or portal session with Stripe
 * or PayPal, so an unbounded caller spends a third-party quota rather than only
 * ours.
 *
 * On CSRF these routes are NOT unprotected, which is worth stating because the
 * route files look like they are. `src/proxy.ts` is the Next 16 proxy
 * middleware (the old `middleware.ts`); its matcher covers `/api/:path*` and it
 * rejects any POST/PUT/PATCH/DELETE without a matching double-submit token
 * before the handler runs. Reading the handler alone gives the wrong answer.
 */

function stubUpstream() {
  const fetchMock = vi.fn(
    async () =>
      ({
        status: 200,
        body: '{"checkout_url":"https://checkout.example/s/1"}',
        headers: new Headers({ 'content-type': 'application/json' }),
      }) as unknown as Response,
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** A distinct client IP per test: rateLimit buckets by IP, so sharing one
 *  would make each test's budget depend on the tests that ran before it. */
function req(url: string, ip: string): Request {
  return new Request(url, {
    method: 'POST',
    headers: { 'x-forwarded-for': ip, 'content-type': 'application/json' },
    body: '{}',
  });
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe.each([
  ['checkout', './checkout/route', 'http://localhost:3000/api/billing/checkout?tier=pro', 10],
  ['portal', './portal/route', 'http://localhost:3000/api/billing/portal', 10],
])('/api/billing/%s rate limiting', (name, modulePath, url, budget) => {
  it('lets an ordinary request through', async () => {
    stubUpstream();
    const { POST } = await import(modulePath);

    const res = await POST(req(url, `10.0.0.1`));

    expect(res.status).not.toBe(429);
  }, 20_000);

  it(`returns 429 with Retry-After once the ${budget}-call budget is spent`, async () => {
    stubUpstream();
    const { POST } = await import(modulePath);
    const ip = `10.0.1.${name === 'checkout' ? 1 : 2}`;

    let last: Response | undefined;
    for (let i = 0; i < budget + 1; i += 1) {
      last = await POST(req(url, ip));
    }

    expect(last?.status).toBe(429);
    expect(last?.headers.get('retry-after')).toBeTruthy();
  }, 20_000);

  it('does not spend one caller budget on another caller', async () => {
    stubUpstream();
    const { POST } = await import(modulePath);
    const noisy = `10.0.2.${name === 'checkout' ? 1 : 2}`;
    const quiet = `10.0.3.${name === 'checkout' ? 1 : 2}`;

    for (let i = 0; i < budget + 1; i += 1) {
      await POST(req(url, noisy));
    }
    const other = await POST(req(url, quiet));

    // Without this, a limiter keyed on nothing would pass the test above while
    // letting one abusive caller lock every customer out of checkout.
    expect(other.status).not.toBe(429);
  }, 20_000);
});
