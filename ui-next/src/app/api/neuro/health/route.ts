import { NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  neuroKeyHeader,
  sanitizeResponseHeaders,
} from '@/lib/security-server';
import { API } from '@/lib/config';

// No parameter: this route reads nothing off the request. It previously took
// `request` only to forward the browser's cookie header upstream, which the
// Neuro backend never reads.
export async function GET() {
  try {
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const upstream = new URL(`${apiBase}${API.NEURO_HEALTH}`);

    const resp = await fetch(upstream.toString(), {
      // No cookie forwarding. sanitizeRequestHeaders' allowlist deliberately
      // omits `cookie`, and these two routes were the only ones bypassing it.
      // The Neuro backend authenticates on X-Neuro-Key alone (neuro/server.py
      // require_neuro_key, which reads request.headers) and touches no cookie
      // anywhere, so the browser's session and CSRF cookies were being handed
      // to a component that never reads them.
      headers: neuroKeyHeader(),
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
