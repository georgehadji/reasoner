import { describe, expect, it } from 'vitest';
import { METHOD_OPTIONS, methodsByCost, presetFor } from './methods';

describe('methodsByCost', () => {
  it('lists every method once, in the tier order', () => {
    for (const tier of ['budget', 'premium']) {
      const menu = methodsByCost(tier);
      expect(menu).toHaveLength(METHOD_OPTIONS.length);
      expect(new Set(menu.map((m) => m.slug)).size).toBe(METHOD_OPTIONS.length);
    }
    expect(methodsByCost('budget').at(-1)?.slug).toBe('article');
    expect(methodsByCost('premium')[2].slug).toBe('scientific');
  });
});

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
