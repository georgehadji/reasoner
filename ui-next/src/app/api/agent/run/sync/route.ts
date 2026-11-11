import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  readJsonBody,
  validateRunRequest,
  extractBearerToken,
  rateLimit,
  proxyErrorResponse,
  SECURITY_SERVER_HASH,
} from '@/lib/security-server';
import { API } from '@/lib/config';

void SECURITY_SERVER_HASH;

/**
 * Proxies POST /api/agent/run/sync — blocks until the pipeline finishes and
 * returns one JSON RunResult. A run can legitimately take up to the
 * pipeline's own cap (currently 600s); this route holds the connection open
 * for the full duration rather than timing out early — see
 * docs/plans/agent-native-reasoner-v2.md §3 for why that is safe on this
 * deployment (a standalone Node server behind Caddy, not a serverless
 * function with an imposed request ceiling).
 */
export async function POST(req: NextRequest) {
  let upstreamUrl: string | undefined;
  try {
    if (!extractBearerToken(req)) {
      return NextResponse.json(
        { error: 'Agent endpoints require Authorization: Bearer <api key>' },
        { status: 401 },
      );
    }

    const limit = rateLimit(req, 'agent-run');
    if (!limit.allowed) {
      return new NextResponse('Too Many Requests', {
        status: 429,
        headers: { 'Retry-After': String(limit.retryAfter) },
      });
    }

    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    upstreamUrl = `${apiBase}${API.AGENT_RUN_SYNC}`;
    const body = await readJsonBody(req);
    const payload = validateRunRequest(body);

    const headers = new Headers(sanitizeRequestHeaders(req.headers));
    headers.set('Content-Type', 'application/json');
    const upstream = await fetch(upstreamUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    const text = await upstream.text();
    const responseHeaders = sanitizeResponseHeaders(upstream);
    responseHeaders.set('Content-Type', 'application/json');
    return new NextResponse(text || '{}', {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (err) {
    return proxyErrorResponse(err, 'Agent run/sync', upstreamUrl);
  }
}
