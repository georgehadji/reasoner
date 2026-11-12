import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  rateLimit,
} from '@/lib/security-server';

export async function POST(req: NextRequest) {
  try {
    // CSRF is enforced upstream of this handler by the proxy middleware
    // (src/proxy.ts). The rate limit is what was missing, matching every other
    // mutating route.
    const limit = rateLimit(req, 'billing-portal');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(`${apiBase}/api/billing/portal`, {
      method: 'POST',
      headers,
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    // The error text names the upstream host; log it here, send a fixed string.
    console.error('Billing portal proxy error:', err instanceof Error ? err.message : err);
    return NextResponse.json({ detail: 'Billing service unavailable' }, { status: 502 });
  }
}
