import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * Tier F1. `sanitizeResponseHeaders` was already well tested as a helper
 * (`security-server.edge-cases.test.ts:315`). What nothing tested was whether
 * the proxy routes actually CALL it — and two of them did not.
 *
 * `/api/neuro/sessions` and `/api/neuro/health` returned `headers: resp.headers`
 * verbatim. Two consequences:
 *
 *   - Hop-by-hop headers a proxy is required to terminate (`transfer-encoding`,
 *     `connection`) were forwarded to the browser.
 *   - `Cache-Control: no-store, private`, which that helper sets on every other
 *     route, was absent. `/api/neuro/sessions` returns one user's memory
 *     sessions; without `no-store` an intermediary is free to cache them and
 *     hand them to the next caller.
 *
 * A helper test cannot catch this class, because the helper was never wrong.
 * The route has to be exercised. These are the first tests in the repo that
 * exercise any route under `src/app/api`.
 */

const upstreamHeaders = {
  'content-type': 'application/json',
  'transfer-encoding': 'chunked',
  connection: 'keep-alive',
  'x-upstream-marker': 'kept',
};

function stubUpstream(status = 200, body = '{"entries":[],"total":0}') {
  // The arg list goes in the generic, not in unused parameters: a zero-arg
  // mock makes `mock.calls[0]` an empty tuple, so reading the init argument is
  // a tsc error, and naming the parameters `_input`/`_init` instead trips
  // no-unused-vars because this config has no leading-underscore exemption.
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
    async () =>
      // A plain object rather than a real Response: constructing a Response
      // with `transfer-encoding` set is refused by undici's header guard.
      ({
        status,
        body,
        headers: new Headers(upstreamHeaders),
      }) as unknown as Response,
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe.each([
  ['sessions', './sessions/route', 'http://localhost:3000/api/neuro/sessions'],
  ['health', './health/route', 'http://localhost:3000/api/neuro/health'],
])('/api/neuro/%s response headers', (_name, modulePath, url) => {
  it('sets Cache-Control: no-store on the proxied response', async () => {
    stubUpstream();
    const { GET } = await import(modulePath);

    const res = await GET(new Request(url));

    expect(res.headers.get('cache-control')).toContain('no-store');
    // 20s, not the 5s default: the first dynamic import of a Next route module
    // pulls in next/server cold and reliably exceeds it on a cold cache.
  }, 20_000);

  it('does not forward hop-by-hop headers to the browser', async () => {
    stubUpstream();
    const { GET } = await import(modulePath);

    const res = await GET(new Request(url));

    expect(res.headers.get('transfer-encoding')).toBeNull();
    expect(res.headers.get('connection')).toBeNull();
  }, 20_000);

  it('still forwards ordinary upstream headers', async () => {
    stubUpstream();
    const { GET } = await import(modulePath);

    const res = await GET(new Request(url));

    // Without this, a route that returned an empty Headers() would satisfy the
    // two assertions above while breaking every real client.
    expect(res.headers.get('x-upstream-marker')).toBe('kept');
    expect(res.headers.get('content-type')).toContain('application/json');
  }, 20_000);
});

describe.each([
  ['sessions', './sessions/route', 'http://localhost:3000/api/neuro/sessions'],
  ['health', './health/route', 'http://localhost:3000/api/neuro/health'],
])('/api/neuro/%s upstream request headers', (_name, modulePath, url) => {
  it('does not forward the browser cookie jar upstream', async () => {
    const fetchMock = stubUpstream();
    const { GET } = await import(modulePath);

    // health's GET takes no parameter at all now, sessions' still reads
    // searchParams. Passing the Request to both is safe: an extra argument to a
    // zero-arity function is ignored, and the assertion below is about what
    // reaches `fetch`, not about what the handler accepts.
    await GET(
      new Request(url, {
        headers: { cookie: 'sb-access-token=secret; csrf_token=abc' },
      }),
    );

    // sanitizeRequestHeaders' allowlist deliberately omits `cookie`, and these
    // two routes were the only ones bypassing it. The Neuro backend
    // authenticates on X-Neuro-Key alone (neuro/server.py require_neuro_key)
    // and reads no cookie anywhere, so this only ever leaked the user's
    // session and CSRF cookies to a component with no use for them.
    const sent = new Headers(fetchMock.mock.calls[0]?.[1]?.headers as HeadersInit);
    expect(sent.get('cookie')).toBeNull();
  }, 20_000);
});
