import { NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  neuroKeyHeader,
  sanitizeResponseHeaders,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const upstream = new URL(`${apiBase}${API.NEURO_SESSIONS}`);
    searchParams.forEach((value, key) => {
      upstream.searchParams.set(key, value);
    });

    const resp = await fetch(upstream.toString(), {
      headers: {
        cookie: request.headers.get('cookie') || '',
        ...neuroKeyHeader(),
      },
    });

    // Every other proxy route returns sanitizeResponseHeaders(resp). These two
    // returned `resp.headers` raw, which forwarded hop-by-hop headers the proxy
    // must terminate (transfer-encoding, connection) and, worse, omitted the
    // `Cache-Control: no-store, private` that helper sets. A session list is
    // per-user data; without no-store an intermediary may cache one user's
    // sessions and serve them to the next.
    return new Response(resp.body, {
      status: resp.status,
      headers: sanitizeResponseHeaders(resp),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Proxy error';
    return NextResponse.json(
      { error: msg, entries: [], total: 0 },
      { status: 502 }
    );
  }
}
