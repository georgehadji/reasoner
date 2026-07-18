import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  readJsonBody,
  rateLimit,
  ValidationError,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function POST(req: NextRequest) {
  try {
    const limit = rateLimit(req, 'error-report');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    // Deliberately CSRF-exempt. This is a diagnostics beacon, not a privileged
    // state change: reportError() is called from error boundaries with a plain
    // fetch and cannot attach a token without fetching /api/csrf from inside a
    // failing page — which breaks precisely during the outages we need reports
    // for, and risks reporting recursion. Forging a report only writes log noise;
    // the rate limit above is the abuse control that actually matters here.
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const body = await readJsonBody(req);

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    headers.set('Content-Type', 'application/json');
    const upstream = await fetch(`${apiBase}${API.ERROR_REPORT}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
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
