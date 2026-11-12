import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  proxyErrorResponse,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function GET(req: NextRequest) {
  try {
    const symbol = req.nextUrl.searchParams.get('symbol');
    if (!symbol || symbol.length > 20 || !/^[A-Za-z0-9.\-]+$/.test(symbol)) {
      return NextResponse.json({ error: 'Invalid symbol parameter' }, { status: 400 });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(
      `${apiBase}${API.STOCKS}?symbol=${encodeURIComponent(symbol)}`,
      { headers }
    );

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    return proxyErrorResponse(err, 'Stocks');
  }
}
