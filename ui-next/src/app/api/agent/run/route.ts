import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  readJsonBody,
  validateRunRequest,
  extractBearerToken,
  rateLimit,
  ValidationError,
  SECURITY_SERVER_HASH,
} from '@/lib/security-server';
import { API } from '@/lib/config';

// Touch SECURITY_SERVER_HASH so Turbopack recompiles this route when it changes.
void SECURITY_SERVER_HASH;

/**
 * Proxies POST /api/agent/run — the streaming agent endpoint.
 *
 * Bearer-only, matching the backend: an agent's API key authenticates the
 * request, so there is no ambient browser credential for a forged
 * cross-origin request to ride on, and CSRF has nothing to defend against
 * here. See ui-next/src/app/api/run/route.ts for the CSRF-gated counterpart
 * this mirrors.
 */
export async function POST(req: NextRequest) {
  let upstreamUrl: string | undefined;
  try {
    if (!extractBearerToken(req)) {
      return NextResponse.json(
        { error: 'Agent endpoints require Authorization: Bearer <api key>' },
        { status: 401 },
      );
    }

    const limit = rateLimit(req, 'agent-run');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    upstreamUrl = `${apiBase}${API.AGENT_RUN}`;
    const body = await readJsonBody(req);
    const payload = validateRunRequest(body);

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    headers.set('Content-Type', 'application/json');
    const upstream = await fetch(upstreamUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    if (err instanceof ValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }

    const msg = err instanceof Error ? err.message : 'Proxy error';
    console.error(`Agent run proxy error upstream=${upstreamUrl || 'N/A'}:`, msg);

    const isConnectionError =
      err instanceof TypeError ||
      msg.toLowerCase().includes('fetch failed') ||
      msg.toLowerCase().includes('econnrefused') ||
      msg.toLowerCase().includes('etimedout');

    if (isConnectionError) {
      return NextResponse.json({ error: 'Backend unreachable', detail: msg }, { status: 504 });
    }
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
