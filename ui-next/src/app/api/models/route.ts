import { NextRequest, NextResponse } from 'next/server';
import {
  getApiBaseUrl,
  validateUpstreamUrl,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
} from '@/lib/security-server';
import { API } from '@/lib/config';

export async function GET(req: NextRequest) {
  try {
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const headers = sanitizeRequestHeaders(req.headers);
    const upstream = await fetch(`${apiBase}${API.MODELS}`, {
      headers,
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: sanitizeResponseHeaders(upstream),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Proxy error';
    const isValidationError = msg.includes('Invalid upstream URL') || msg.includes('disallowed port') || msg.includes('private network');
    return NextResponse.json({ error: msg }, { status: isValidationError ? 400 : 502 });
  }
}
