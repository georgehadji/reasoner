import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  rateLimit,
  requireCsrfToken,
  ValidationError,
  SECURITY_SERVER_HASH,
} from '@/lib/security-server';
import { API } from '@/lib/config';

// Touch SECURITY_SERVER_HASH so Turbopack recompiles this route when it changes.
void SECURITY_SERVER_HASH;

/**
 * Proxy for `API.PIPELINE_RESUME`, which api-client.ts calls to resume a saved
 * run. Every `API.*` constant needs a matching route file here or the call 404s
 * against Next rather than reaching the backend -- this one was missed when the
 * sibling proxies landed, so resume has been dead since.
 *
 * Streams the upstream SSE body straight through: the response is
 * text/event-stream, so it must not be buffered or re-encoded.
 */
export async function POST(
  req: NextRequest,
  context: { params: Promise<{ pipelineId: string }> },
) {
  let upstreamUrl: string | undefined;
  try {
    const limit = rateLimit(req, 'pipeline-resume');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    await requireCsrfToken(req);
    const { pipelineId } = await context.params;
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    upstreamUrl = `${apiBase}${API.PIPELINE_RESUME(pipelineId)}`;

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    const upstream = await fetch(upstreamUrl, {
      method: 'POST',
      headers,
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    if (err instanceof ValidationError) {
      return NextResponse.json({ error: err.message }, { status: 400 });
    }

    const msg = err instanceof Error ? err.message : 'Proxy error';
    const errName = err instanceof Error ? err.constructor.name : 'Unknown';

    console.error(`Proxy error [${errName}] upstream=${upstreamUrl || 'N/A'}:`, msg);

    // Connection-level errors (network, DNS, timeout) -> 504 Gateway Timeout
    const isConnectionError =
      err instanceof TypeError ||
      msg.toLowerCase().includes('fetch failed') ||
      msg.toLowerCase().includes('network') ||
      msg.toLowerCase().includes('econnrefused') ||
      msg.toLowerCase().includes('etimedout');

    if (isConnectionError) {
      return NextResponse.json({ error: 'Backend unreachable', detail: msg }, { status: 504 });
    }

    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
