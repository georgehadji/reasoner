import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  rateLimit,
  proxyErrorResponse,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function DELETE(req: NextRequest) {
  try {
    const limit = rateLimit(req, 'cache');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(`${apiBase}${API.CACHE}`, {
      method: 'DELETE',
      headers,
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    return proxyErrorResponse(err, 'Cache');
  }
}
