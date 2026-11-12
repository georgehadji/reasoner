import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
} from '@/lib/security-server';

export async function POST(req: NextRequest) {
  try {
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const body = await req.arrayBuffer();

    const upstream = await fetch(`${apiBase}/api/billing/webhook`, {
      method: 'POST',
      headers,
      body,
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    // The error text names the upstream host; log it here, send a fixed string.
    console.error('Stripe webhook proxy error:', err instanceof Error ? err.message : err);
    return NextResponse.json({ detail: 'Billing service unavailable' }, { status: 502 });
  }
}
