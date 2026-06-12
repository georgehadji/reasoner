import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  readJsonBody,
  requireCsrfToken,
  rateLimit,
  ValidationError,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function POST(req: NextRequest) {
  try {
    const limit = rateLimit(req, 'generate-image');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    await requireCsrfToken(req);
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const body = await readJsonBody(req);

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    headers.set('Content-Type', 'application/json');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120_000); // 120s — covers 90s backend + network overhead
    let upstream: Response;
    try {
      upstream = await fetch(`${apiBase}${API.GENERATE_IMAGE}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    if (err instanceof ValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }
    const isTimeout = err instanceof DOMException && err.name === 'AbortError';
    if (isTimeout) {
      return NextResponse.json(
        { error: 'Image generation timed out. Try a simpler prompt or fewer images.' },
        { status: 504 }
      );
    }
    console.error('Generate image proxy error:', err);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
