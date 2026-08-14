import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  rateLimit,
  readJsonBody,
  requireCsrfToken,
  ValidationError,
} from './security-server';

/**
 * Shared JSON proxy for backend routes the browser calls.
 *
 * Every Next route handler that forwards to FastAPI needs the same five steps
 * — validate the upstream origin, rate limit, require CSRF on mutations,
 * strip unsafe headers both ways, and translate failures into a status the
 * client can act on. Repeating that per route is how one of them ends up
 * missing the CSRF check.
 */

interface ProxyOptions {
  /** Path on the backend, e.g. `/api/credits`. Query string is forwarded. */
  path: string;
  method?: 'GET' | 'POST' | 'DELETE' | 'PATCH';
  /** Rate limit bucket name. Mutations should always set one. */
  rateLimitKey?: string;
  /** Forward the incoming query string to the backend. */
  forwardQuery?: boolean;
}

const MUTATING_METHODS = new Set(['POST', 'DELETE', 'PATCH', 'PUT']);

export async function proxyJson(
  req: NextRequest,
  { path, method = 'GET', rateLimitKey, forwardQuery = false }: ProxyOptions,
): Promise<Response> {
  try {
    if (rateLimitKey) {
      const limit = rateLimit(req, rateLimitKey);
      if (!limit.allowed) {
        return NextResponse.json(
          { error: 'Too many requests' },
          { status: 429, headers: { 'Retry-After': String(limit.retryAfter) } },
        );
      }
    }

    if (MUTATING_METHODS.has(method)) {
      await requireCsrfToken(req);
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = new Headers(sanitizeRequestHeaders(req.headers));

    let body: string | undefined;
    if (method === 'POST' || method === 'PATCH') {
      const parsed = await readJsonBody(req);
      body = JSON.stringify(parsed ?? {});
      headers.set('Content-Type', 'application/json');
    }

    const query = forwardQuery ? req.nextUrl.search : '';
    const upstream = await fetch(`${apiBase}${path}${query}`, { method, headers, body });

    const text = await upstream.text();
    const responseHeaders = sanitizeResponseHeaders(upstream);
    responseHeaders.set('Content-Type', 'application/json');

    return new NextResponse(text || '{}', {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (err) {
    if (err instanceof ValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    const message = err instanceof Error ? err.message : 'Proxy error';
    const isUpstreamConfigError =
      message.includes('Invalid upstream URL') ||
      message.includes('disallowed port') ||
      message.includes('private network');
    return NextResponse.json({ error: message }, { status: isUpstreamConfigError ? 400 : 502 });
  }
}
