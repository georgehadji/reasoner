import { NextRequest } from 'next/server';
import { proxyJson } from '@/lib/api-proxy';
import { API } from '@/lib/config';

export async function POST(req: NextRequest) {
  return proxyJson(req, {
    path: API.PROVENANCE_SCRUB,
    method: 'POST',
    rateLimitKey: 'provenance-scrub',
  });
}
