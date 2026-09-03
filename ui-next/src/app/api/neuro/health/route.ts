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
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const upstream = new URL(`${apiBase}${API.NEURO_HEALTH}`);

    const resp = await fetch(upstream.toString(), {
      headers: {
        cookie: request.headers.get('cookie') || '',
        ...neuroKeyHeader(),
      },
    });

    if (resp.status === 404) {
      // Neuro router not mounted in running backend — return graceful fallback
      return NextResponse.json({
        status: 'unavailable',
        version: 'unknown',
        timestamp: new Date().toISOString(),
        reasoning: { healthy: false },
        embedding: { healthy: false },
        agents_configured: [],
        default_persona: 'default',
        sessions: { hot: 0, warm: 0, cold: 0 },
      });
    }

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
  } catch {
    return NextResponse.json({
      status: 'unavailable',
      version: 'unknown',
      timestamp: new Date().toISOString(),
      reasoning: { healthy: false },
      embedding: { healthy: false },
      agents_configured: [],
      default_persona: 'default',
      sessions: { hot: 0, warm: 0, cold: 0 },
    }, { status: 503 });
  }
}
