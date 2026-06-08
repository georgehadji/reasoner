import { NextResponse } from 'next/server';
import { getApiBaseUrl, validateUpstreamUrl } from '@/lib/security-server';

export async function GET() {
  try {
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    const resp = await fetch(`${apiBase}/`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    // The root endpoint is always lightweight — any 2xx-5xx means the backend is alive
    return new Response(resp.body, { status: resp.status });
  } catch {
    return NextResponse.json(
      { status: 'unhealthy', error: 'Backend unreachable' },
      { status: 503 },
    );
  }
}
