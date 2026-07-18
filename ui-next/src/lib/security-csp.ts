import { REASONER_WS_HOSTS, REASONER_WS_PORTS } from './server-config';

const DEFAULT_WS_URL = 'ws://127.0.0.1:8003/ws';

function buildConnectSrc(wsUrl: string): string {
  const wsOrigins = new Set<string>();
  const addOrigins = (host: string, port: string) => {
    wsOrigins.add(`ws://${host}:${port}`);
    wsOrigins.add(`wss://${host}:${port}`);
  };
  for (const port of REASONER_WS_PORTS) {
    for (const host of REASONER_WS_HOSTS) {
      addOrigins(host, port);
    }
  }

  if (wsUrl) {
    try {
      const u = new URL(wsUrl);
      const port = u.port || REASONER_WS_PORTS[0];
      addOrigins(u.hostname, port);
    } catch {
      // Fall back to the explicit host/port allowlist above.
    }
  }

  return `connect-src 'self' ${[...wsOrigins].join(' ')}`;
}

export function buildContentSecurityPolicy(options?: {
  allowUnsafeScripts?: boolean;
  wsUrl?: string;
}): string {
  const allowUnsafeScripts = options?.allowUnsafeScripts ?? false;
  const wsUrl = options?.wsUrl ?? process.env.NEXT_PUBLIC_WS_URL ?? DEFAULT_WS_URL;
  const scriptSrc = allowUnsafeScripts
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
    : "script-src 'self'";

  return [
    "default-src 'self'",
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    buildConnectSrc(wsUrl),
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ');
}
