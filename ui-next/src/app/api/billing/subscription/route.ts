import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
} from '@/lib/security-server';

const DEFAULT_FREE_SUBSCRIPTION = { tier: 'free', status: 'active' };

export async function GET(req: NextRequest) {
  try {
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(`${apiBase}/api/billing/subscription`, { headers });

    // Auth not configured or route not found → return free tier default
    if (upstream.status === 401 || upstream.status === 403 || upstream.status === 404) {
      return NextResponse.json(DEFAULT_FREE_SUBSCRIPTION);
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch {
    // Backend unreachable → return free tier default so UI renders without errors
    return NextResponse.json(DEFAULT_FREE_SUBSCRIPTION);
  }
}
