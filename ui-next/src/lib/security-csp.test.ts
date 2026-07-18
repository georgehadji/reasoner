import { describe, expect, it } from 'vitest';
import { buildContentSecurityPolicy } from './security-csp';

describe('buildContentSecurityPolicy', () => {
  it('allows blob previews and both websocket schemes for localhost', () => {
    const csp = buildContentSecurityPolicy({
      wsUrl: 'wss://localhost:8003/ws',
      allowUnsafeScripts: false,
    });

    expect(csp).toContain("img-src 'self' data: blob:");
    expect(csp).toContain('ws://localhost:8003');
    expect(csp).toContain('wss://localhost:8003');
  });

  it('includes production-safe script policy when unsafe scripts are disabled', () => {
    const csp = buildContentSecurityPolicy({
      wsUrl: 'ws://127.0.0.1:8003/ws',
      allowUnsafeScripts: false,
    });

    expect(csp).toContain("script-src 'self'");
    expect(csp).not.toContain("script-src 'self' 'unsafe-inline'");
    expect(csp).not.toContain("script-src 'self' 'unsafe-eval'");
  });
});
