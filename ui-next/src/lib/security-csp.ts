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

/**
 * `script-src` has to permit inline script, and this is not a preference.
 *
 * Next's App Router ships the RSC flight payload to the browser as inline
 * `<script>self.__next_f.push(...)</script>` blocks — on this app's home page
 * that is 4 inline blocks totalling ~100KB, alongside next-themes' FOUC
 * script. Under a bare `script-src 'self'` the browser refuses all of them,
 * React fails to hydrate with error #412, and the entire site — the chat
 * product included — renders as dead HTML with no client JS at all. That is
 * what this file emitted in production until 2026-08: `next.config.ts` and
 * `proxy.ts` both served `script-src 'self'`, and nginx adds no CSP of its
 * own, so nothing anywhere relaxed it.
 *
 * The two alternatives were measured, not assumed:
 *
 *   - **Hashes.** Not viable. The flight payload is ~100KB, differs per page,
 *     and changes every build; it cannot go in a header.
 *   - **Per-request nonce.** Works, but only for dynamically rendered pages.
 *     This app prerenders 85 routes; their HTML is baked at build time with no
 *     nonce on its script tags, so a nonce'd policy blocks them exactly as
 *     before — verified by building with one and finding zero nonce'd tags in
 *     the output. `'strict-dynamic'` makes it worse, because it voids the
 *     `'self'` that currently lets the external chunks load. Adopting a nonce
 *     therefore means giving up static rendering on all 85 routes.
 *
 * So `'unsafe-inline'` it is, and it is a real cost: an attacker who can
 * inject markup into a page can execute script, which is the main thing
 * `script-src` otherwise buys. The compensating controls are elsewhere —
 * React's escaping, `sanitize_for_prompt`, the markdown renderer's allowlist —
 * and `object-src`/`base-uri`/`frame-ancestors` still hold the rest of the
 * line.
 *
 * To upgrade: make the routes dynamic and switch to a nonce. That is a
 * deliberate trade of static rendering for a stricter policy, not a cleanup.
 */
export function buildContentSecurityPolicy(options?: {
  /**
   * Dev only. Turbopack's HMR client calls `eval()`; production never should.
   * Inline script is NOT gated on this — see the note above, it is required
   * in every environment.
   */
  allowUnsafeEval?: boolean;
  wsUrl?: string;
}): string {
  const allowUnsafeEval = options?.allowUnsafeEval ?? false;
  const wsUrl = options?.wsUrl ?? process.env.NEXT_PUBLIC_WS_URL ?? DEFAULT_WS_URL;
  const scriptSrc = allowUnsafeEval
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
    : "script-src 'self' 'unsafe-inline'";

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
    /* Inherited from default-src, but stated explicitly because it is one of
       the directives still doing real work now that script-src permits inline:
       it stops an injected <object>/<embed> being used to run plugin content. */
    "object-src 'none'",
  ].join('; ');
}
