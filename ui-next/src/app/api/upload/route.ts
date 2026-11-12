import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
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
    const limit = rateLimit(req, 'upload');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    await requireCsrfToken(req);
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    upstreamUrl = `${apiBase}${API.UPLOAD}`;

    // Forward the multipart body directly — do NOT parse it in Next.js
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(upstreamUrl, {
      method: 'POST',
      headers,
      body: req.body,
      // @ts-expect-error — duplex is required for streaming request bodies in Node 18+
      duplex: 'half',
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    return proxyErrorResponse(err, 'Upload', upstreamUrl);
  }
}
