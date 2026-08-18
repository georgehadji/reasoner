import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { SHOWCASE_IMAGES } from './image-showcase';

/**
 * The showcase is a real captured run, so the risk is drift rather than logic:
 * a file gets moved or optimised away and the home page renders four broken
 * images. These assert the two things that would actually break.
 */
describe('image showcase', () => {
  const publicDir = join(process.cwd(), 'public');

  it('every referenced image exists on disk', () => {
    for (const { src } of SHOWCASE_IMAGES) {
      expect(existsSync(join(publicDir, src)), `missing ${src}`).toBe(true);
    }
  });

  it('stays small enough to ship on a landing page', () => {
    const total = SHOWCASE_IMAGES.reduce(
      (sum, { src }) => sum + statSync(join(publicDir, src)).size,
      0,
    );
    // Captured at ~110KB total. 400KB leaves room to re-capture without
    // silently shipping the multi-megabyte originals the models return.
    expect(total).toBeLessThan(400_000);
  });

  it('names four distinct models', () => {
    const models = new Set(SHOWCASE_IMAGES.map((image) => image.model));
    expect(models.size).toBe(4);
  });
});
