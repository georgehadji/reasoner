import { describe, expect, it } from 'vitest';
import { isLocalHost } from './local-host';

describe('isLocalHost', () => {
  it.each(['localhost', '127.0.0.1', '[::1]', '::1', 'app.localhost'])('%s is local', (host) => {
    expect(isLocalHost(host)).toBe(true);
  });

  it.each(['reasoner.app', 'localhost.evil.com', '10.0.0.5', ''])('%s is not local', (host) => {
    expect(isLocalHost(host)).toBe(false);
  });
});
