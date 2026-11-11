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
    const location = req.nextUrl.searchParams.get('location');
    if (!location || location.length > 100 || !/^[\p{L}\p{N}\s,.\-]+$/u.test(location)) {
      return NextResponse.json({ error: 'Invalid location parameter' }, { status: 400 });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(
      `${apiBase}${API.WEATHER}?location=${encodeURIComponent(location)}`,
      { headers }
    );

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    return proxyErrorResponse(err, 'Weather');
  }
}
