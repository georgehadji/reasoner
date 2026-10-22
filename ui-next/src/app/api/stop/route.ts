import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  requireCsrfToken,
  rateLimit,
  ValidationError,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function POST(req: NextRequest) {
  try {
    const limit = rateLimit(req, 'stop');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    await requireCsrfToken(req);
    // Only ever a single-run stop (UI-4). Upstream, a bare /api/stop is the
    // admin "stop every user's run"; the browser has no reason to send it.
    const runId = req.nextUrl.searchParams.get('run_id');
    if (!runId) throw new ValidationError('run_id is required');
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(`${apiBase}${API.STOP}?run_id=${encodeURIComponent(runId)}`, {
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
