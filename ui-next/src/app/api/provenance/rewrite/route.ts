import { NextRequest } from 'next/server';
import { proxyJson } from '@/lib/api-proxy';
import { API } from '@/lib/config';

// Layer B (statistical rewrite) is not yet available -- the backend always
// returns 501 here until Phase 6 binds a rewriter. The route still exists so
// the frontend has one stable path to call once it ships.
export async function POST(req: NextRequest) {
  return proxyJson(req, {
    path: API.PROVENANCE_REWRITE,
    method: 'POST',
    rateLimitKey: 'provenance-rewrite',
  });
}
