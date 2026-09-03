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
    // CSRF is already enforced for this route by the proxy middleware
    // (src/proxy.ts), whose matcher covers /api/:path* and which rejects any
    // POST without a matching double-submit token. What was missing is the
    // rate limit every other mutating route carries: each call creates a
    // checkout session with Stripe or PayPal, so an unbounded caller spends a
    // third-party quota.
    const limit = rateLimit(req, 'billing-checkout');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const { searchParams } = new URL(req.url);
    
    // Extract tier and provider from query params
    let tier = searchParams.get('tier');
    let provider = searchParams.get('provider');

    // If not in query params, try to read from JSON body (for UpgradeModal)
    if (!tier) {
      try {
        const body = await req.json();
        tier = body.tier;
        if (!provider) provider = body.provider;
      } catch {
        // Body might be empty or not JSON, ignore
      }
    }

    if (!tier) {
      return NextResponse.json({ detail: 'Missing tier parameter' }, { status: 400 });
    }

    const upstreamUrl = new URL(`${apiBase}/api/billing/checkout`);
    upstreamUrl.searchParams.set('tier', tier);
    if (provider) upstreamUrl.searchParams.set('provider', provider);

    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(upstreamUrl.toString(), {
      method: 'POST',
      headers,
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Proxy error';
    return NextResponse.json({ detail: msg }, { status: 502 });
  }
}
