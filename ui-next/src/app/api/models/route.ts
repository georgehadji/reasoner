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
    return proxyErrorResponse(err, 'Models');
  }
}
