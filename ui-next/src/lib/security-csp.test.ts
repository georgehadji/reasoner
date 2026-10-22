import { describe, expect, it } from 'vitest';
import { buildContentSecurityPolicy } from './security-csp';

describe('buildContentSecurityPolicy', () => {
  it('allows blob previews and both websocket schemes for localhost', () => {
    const csp = buildContentSecurityPolicy({
      wsUrl: 'wss://localhost:8003/ws',
      allowUnsafeEval: false,
    });

    expect(csp).toContain("img-src 'self' data: blob:");
    expect(csp).toContain('ws://localhost:8003');
    expect(csp).toContain('wss://localhost:8003');
  });

  /**
   * This assertion is inverted from what it used to say, and the inversion is
   * the point. The old test required production to emit a bare
   * `script-src 'self'`, which reads like the strictest possible policy and
   * was in fact a site-wide outage: Next's App Router delivers its RSC payload
   * in inline <script> blocks, so that policy blocked hydration on every route
   * and left the app as dead HTML. The test passed the whole time, because it
   * only ever checked the string.
   *
   * Inline script is now a requirement of the framework, not a lapse. If a
   * future change drops 'unsafe-inline' to tighten the policy, this fails —
   * which is the outcome that was missing.
   */
  /**
   * UI-6. `connect-src` allowed only 'self' and the WS hosts, so in production
   * the browser blocked every Supabase auth call (sign-in, sign-up, token
   * refresh) and the Sentry ingest. A `wss://` URL with no port also got the
   * dev port 8000 instead of 443.
   */
  it('allows the Supabase origin for auth calls', () => {
    const csp = buildContentSecurityPolicy({
      wsUrl: 'ws://127.0.0.1:8003/ws',
      supabaseUrl: 'https://x.supabase.co/',
    });
    expect(csp).toMatch(/connect-src [^;]*https:\/\/x\.supabase\.co(?=[ ;]|$)/);
  });

  it('allows the Sentry ingest origin taken from the DSN', () => {
    const csp = buildContentSecurityPolicy({
      wsUrl: 'ws://127.0.0.1:8003/ws',
      sentryDsn: 'https://key@o123.ingest.sentry.io/456',
    });
    expect(csp).toMatch(/connect-src [^;]*https:\/\/o123\.ingest\.sentry\.io(?=[ ;]|$)/);
  });

  it.each([
    ['wss://app.example/ws', 'wss://app.example:443'],
    ['ws://app.example/ws', 'ws://app.example:80'],
    ['wss://app.example:9443/ws', 'wss://app.example:9443'],
  ])('gives %s its scheme default port', (wsUrl, expected) => {
    const csp = buildContentSecurityPolicy({ wsUrl });
    expect(csp).toContain(expected);
    expect(csp).not.toContain('app.example:8000');
  });

  it('ignores a malformed Supabase URL', () => {
    const csp = buildContentSecurityPolicy({ wsUrl: 'ws://127.0.0.1:8003/ws', supabaseUrl: 'not a url' });
    expect(csp).toContain("connect-src 'self'");
  });

  it('permits the inline script Next needs to hydrate', () => {
    const csp = buildContentSecurityPolicy({
      wsUrl: 'ws://127.0.0.1:8003/ws',
      allowUnsafeEval: false,
    });

    expect(csp).toContain("script-src 'self' 'unsafe-inline'");
  });

  it('withholds unsafe-eval unless dev explicitly asks for it', () => {
    const prod = buildContentSecurityPolicy({ wsUrl: 'ws://127.0.0.1:8003/ws' });
    expect(prod).not.toContain("'unsafe-eval'");

    const dev = buildContentSecurityPolicy({
      wsUrl: 'ws://127.0.0.1:8003/ws',
      allowUnsafeEval: true,
    });
    expect(dev).toContain("script-src 'self' 'unsafe-inline' 'unsafe-eval'");
  });

  it('keeps the directives that still constrain an injected script', () => {
    const csp = buildContentSecurityPolicy({ wsUrl: 'ws://127.0.0.1:8003/ws' });

    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("default-src 'self'");
  });
});
