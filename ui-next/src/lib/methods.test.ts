import { describe, expect, it } from 'vitest';
import { presetFor } from './methods';

describe('presetFor', () => {
  it('lets HyperGate choose when no method is picked', () => {
    expect(presetFor(null, false, 'budget')).toBe('auto-budget');
    expect(presetFor(null, true, 'premium')).toBe('auto-western-premium');
  });

  it("uses the picked method's preset family", () => {
    expect(presetFor('debate', false, 'premium')).toBe('debate-premium');
    expect(presetFor('self-refine', true, 'budget')).toBe('self-refine-western-budget');
  });
});
