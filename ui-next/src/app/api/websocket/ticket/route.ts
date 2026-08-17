import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  rateLimit,
  requireCsrfToken,
  ValidationError,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function POST(req: NextRequest) {
  try {
    const limit = rateLimit(req, 'websocket-ticket');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    await requireCsrfToken(req);
    const apiBase = validateUpstreamUrl(getApiBaseUrl());

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    const upstream = await fetch(`${apiBase}${API.WEBSOCKET_TICKET}`, {
      method: 'POST',
      headers,
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
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
