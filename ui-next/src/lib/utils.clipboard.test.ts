// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { copyToClipboard } from './utils';

/** UI-12. The chat call sites bypassed this helper and ignored the rejection. */
describe('copyToClipboard', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('resolves false instead of rejecting when writeText is refused', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn(async () => { throw new Error('denied'); }) } });
    await expect(copyToClipboard('hi')).resolves.toBe(false);
  });
});
