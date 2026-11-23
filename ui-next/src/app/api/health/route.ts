import { NextResponse } from 'next/server';
import { getApiBaseUrl, proxyTopologyUndeclared, validateUpstreamUrl } from '@/lib/security-server';

export async function GET() {
  try {
    const apiBase = validateUpstreamUrl(getApiBaseUrl());
    const controller = new AbortController();
    // The backend's first Postgres probe may take up to 5s to open its pool.
    const timeoutId = setTimeout(() => controller.abort(), 6000);
    // /api/health, not the root: /status reads `status` and `checks`, which the
    // root (a link list) never had, so the page read "Service disruption" while
    // the backend was up. It answers 200 even when unhealthy, so callers that
    // only test `resp.ok` for liveness read it as before.
    const resp = await fetch(`${apiBase}/api/health`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    // OPS-9: flag an undeclared proxy chain so monitoring sees it.
    const headers = proxyTopologyUndeclared() ? { 'X-Proxy-Topology': 'undeclared' } : undefined;
    return new Response(resp.body, { status: resp.status, headers });
  } catch {
    return NextResponse.json(
      { status: 'unhealthy', error: 'Backend unreachable' },
      { status: 503 },
    );
  }
}
