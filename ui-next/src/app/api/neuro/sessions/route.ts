import { NextResponse } from 'next/server';
import { getApiBaseUrl, validateUpstreamUrl } from '@/lib/security-server';
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
      },
    });

    return new Response(resp.body, {
      status: resp.status,
      headers: resp.headers,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Proxy error';
    return NextResponse.json(
      { error: msg, entries: [], total: 0 },
      { status: 502 }
    );
  }
}
