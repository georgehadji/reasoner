import { describe, expect, it } from 'vitest';
import EVENTS from './demo-run.json';
import { CLAIM_SPECIMENS, LABELLED_CLAIMS, RUN, RUN_MODELS, SCORE_AXES } from './demo-record';

/**
 * The home page states every one of its figures by counting this record. If the
 * parser silently returns nothing the page still renders — just empty and
 * wrong — so the check that matters is that the run actually parsed.
 */
describe('demo record', () => {
  it('parses all five phases with real durations', () => {
    expect(RUN.phases).toHaveLength(5);
    expect(RUN.phases.every((p) => p.seconds > 0)).toBe(true);
  });

  it('carries the run identity and ledger', () => {
    expect(RUN.preset).toBe('multi-perspective-budget');
    expect(RUN.ledger.tokensTotal).toBeGreaterThan(0);
    expect(RUN.ledger.costUsd).toBeGreaterThan(0);
    expect(RUN_MODELS.length).toBeGreaterThan(1);
  });

  it('scores every position on every axis, with pruning', () => {
    expect(RUN.scores).toHaveLength(4);
    for (const score of RUN.scores) {
      for (const { key } of SCORE_AXES) expect(typeof score[key]).toBe('number');
    }
    expect(RUN.scores.some((s) => s.retained)).toBe(true);
    expect(RUN.scores.some((s) => !s.retained)).toBe(true);
  });

  it('extracts sources, positions and stress tests', () => {
    expect(RUN.sources.length).toBeGreaterThan(0);
    expect(RUN.sources[0].domain).not.toContain('/');
    expect(RUN.positions).toHaveLength(4);
    expect(RUN.positions.every((p) => p.excerpt.length > 0)).toBe(true);
    expect(RUN.stress.length).toBeGreaterThan(0);
  });

  it('splits the synthesis into blocks and numbers its citations once each', () => {
    expect(RUN.synthesis.length).toBeGreaterThan(5);
    expect(RUN.synthesis.some((b) => b.kind === 'heading')).toBe(true);

    const cited = RUN.synthesis.flatMap((b) =>
      b.kind === 'para' || b.kind === 'item' ? b.segments : [],
    );
    expect(cited.some((s) => s.kind === 'cite')).toBe(true);
    expect(cited.some((s) => s.kind === 'label')).toBe(true);

    // Citation numbers are 1..n over distinct URLs — the reference list and the
    // superscripts in the prose are generated from the same map.
    expect(RUN.citations.map((c) => c.index)).toEqual(
      RUN.citations.map((_, i) => i + 1),
    );
    expect(new Set(RUN.citations.map((c) => c.url)).size).toBe(RUN.citations.length);
  });
});

/**
 * The home page's agents section quotes three of these as its exhibit. Two
 * things have to hold for that to be honest: they must come out of the run
 * rather than out of an editor, and they must be readable once lifted away
 * from the paragraph that produced them.
 */
describe('labelled claims', () => {
  const RAW = JSON.stringify(EVENTS);

  it('finds labelled claims across the run', () => {
    expect(LABELLED_CLAIMS.length).toBeGreaterThan(5);
    expect(new Set(LABELLED_CLAIMS.map((c) => c.label)).size).toBe(3);
  });

  it('shows one specimen per label, in descending confidence', () => {
    expect(CLAIM_SPECIMENS.map((c) => c.label)).toEqual([
      'VERIFIED',
      'HYPOTHESIS',
      'UNKNOWN',
    ]);
  });

  it('quotes the run rather than paraphrasing it', () => {
    for (const { claim } of CLAIM_SPECIMENS) {
      // The opening connective is stripped and the next word capitalised, so
      // the tail is the part that must survive verbatim.
      expect(RAW).toContain(claim.slice(-60));
    }
  });

  it('picks specimens that stand on their own', () => {
    for (const { claim } of CLAIM_SPECIMENS) {
      expect(claim).not.toMatch(/^(however|finally|first|second|ultimately)\b/i);
      expect(claim).not.toMatch(/\b(these|those|the proposal)\b/i);
      expect(claim.length).toBeGreaterThan(40);
    }
  });
});
