/**
 * Server-side configuration for Next.js API route proxies.
 * Points to the Reasoner FastAPI backend.
 */
export const REASONER_API_BASE =
  process.env.REASONER_API_URL || 'http://127.0.0.1:8003';

export const REASONER_WS_PORTS = ['8000', '8003'];
export const REASONER_WS_HOSTS = ['localhost', '127.0.0.1'];
export const REASONER_WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8003/ws';
