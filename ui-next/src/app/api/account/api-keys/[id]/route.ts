import { NextRequest, NextResponse } from 'next/server';
import { proxyJson } from '@/lib/api-proxy';
import { API } from '@/lib/config';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // Reject anything that is not a UUID here rather than forwarding it: the id
  // becomes part of the upstream path, so it must never carry path segments.
  if (!UUID_PATTERN.test(id)) {
    return NextResponse.json({ error: 'Invalid key id' }, { status: 400 });
  }

  return proxyJson(req, {
    path: API.API_KEY_BY_ID(id),
    method: 'DELETE',
    rateLimitKey: 'api-key-revoke',
  });
}
