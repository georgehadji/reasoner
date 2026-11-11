import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  readJsonBody,
  validateRunFollowupRequest,
  requireCsrfToken,
  rateLimit,
  proxyErrorResponse,
  SECURITY_SERVER_HASH,
} from '@/lib/security-server';
import { API } from '@/lib/config';

// Touch SECURITY_SERVER_HASH so Turbopack recompiles this route when it changes.
void SECURITY_SERVER_HASH;

export async function POST(req: NextRequest) {
  let upstreamUrl: string | undefined;
  try {
    const limit = rateLimit(req, 'run');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    await requireCsrfToken(req);
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    upstreamUrl = `${apiBase}${API.RUN_FOLLOWUP}`;
    const body = await readJsonBody(req);
    const payload = validateRunFollowupRequest(body);

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    headers.set('Content-Type', 'application/json');
    const upstream = await fetch(upstreamUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    if (upstream.status === 422) {
      const clone = upstream.clone();
      const text = await clone.text().catch(() => '');
      console.error('Upstream 422 response body:', text);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    return proxyErrorResponse(err, 'Run followup', upstreamUrl);
  }
}
