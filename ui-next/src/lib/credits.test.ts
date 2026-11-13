import { describe, expect, it } from 'vitest';
import { runsPerMonth } from './credits';

describe('runsPerMonth', () => {
  it('reads an open-ended range from zero as a floor', () => {
    expect(runsPerMonth(500, [0, 2])).toBe('250 or more');
  });

  it('reads a fixed cost as an approximate count', () => {
    expect(runsPerMonth(500, [20, 20])).toBe('about 25');
  });

  it('reads a range as fewest to most, rounded down', () => {
    expect(runsPerMonth(500, [150, 300])).toBe('1–3');
    expect(runsPerMonth(25_000, [150, 300])).toBe('83–166');
  });
});
