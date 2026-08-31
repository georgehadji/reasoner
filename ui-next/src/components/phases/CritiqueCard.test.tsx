import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import EVENTS from '@/lib/demo-run.json';
import { CritiqueCard } from './CritiqueCard';

/**
 * The critique phase is where the product's least imitable claim lives: it keeps
 * the positions it rejected instead of returning only the winner. Migration step 4
 * moved that from a card stack to a real score matrix on the paid surface.
 *
 * The fragile part is not the table — it is the mapping into it. The live payload
 * is snake_case, RunScore is camelCase, and `retained` has no live equivalent at
 * all (the backend marks only `is_top`). A rename on either side turns every axis
 * into 0.0 and every column grey, silently, with no type error. So this feeds the
 * ACTUAL captured payload through the real component rather than a hand-written
 * fixture — a fixture would be updated alongside the rename and prove nothing.
 */

interface RawScore {
  perspective: string;
  logical_consistency: number;
  evidence_support: number;
  failure_resilience: number;
  feasibility: number;
  total: number;
  bias_flags: string[];
  steel_man: string;
  is_top: boolean;
}

/** The critique payload as the pipeline actually emitted it. */
function critiquePayload(): { scores: RawScore[] } {
  const events = EVENTS as unknown as Array<Record<string, unknown>>;
  for (const event of events) {
    const payload = (event.payload ?? event.data) as Record<string, unknown> | undefined;
    if (payload && Array.isArray(payload.scores) && payload.scores.length) {
      return payload as unknown as { scores: RawScore[] };
    }
  }
  throw new Error('demo-run.json carries no critique scores — fixture drifted');
}

describe('CritiqueCard', () => {
  const payload = critiquePayload();

  it('renders the live payload as a real table, not a picture of one', () => {
    render(<CritiqueCard data={payload} />);
    // A <table> keeps its meaning with CSS off, on paper, and in a screen reader.
    expect(screen.getByRole('table')).toBeTruthy();
  });

  it('maps every snake_case axis across, so no column collapses to zero', () => {
    render(<CritiqueCard data={payload} />);
    const table = screen.getByRole('table');

    // The winner's own axis values must appear. If logical_consistency were
    // renamed or mis-mapped, num() would floor it to 0 and this would fail.
    const top = payload.scores.find((s) => s.is_top) ?? payload.scores[0];
    for (const axis of [
      top.logical_consistency,
      top.evidence_support,
      top.failure_resilience,
      top.feasibility,
    ]) {
      expect(within(table).getAllByText(axis.toFixed(1)).length).toBeGreaterThan(0);
    }
  });

  it('keeps the rejected positions in place rather than omitting them', () => {
    render(<CritiqueCard data={payload} />);
    const table = screen.getByRole('table');

    // Every position gets a column, winners and losers alike. Showing the
    // dissent the run threw away is the point of the figure.
    for (const score of payload.scores) {
      expect(within(table).getByText(score.perspective)).toBeTruthy();
    }

    const pruned = payload.scores.filter((s) => !s.is_top);
    if (pruned.length) {
      expect(within(table).getAllByText('Pruned').length).toBe(pruned.length);
    }
    expect(within(table).getAllByText('Carried forward').length).toBe(
      payload.scores.filter((s) => s.is_top).length,
    );
  });

  it('renders a penalised zero total rather than treating it as missing data', () => {
    // The captured run has a position scoring 5/3/6/5 across the axes whose
    // total is 0 after penalties. It is the single best argument for the table
    // existing — a position can look respectable on every axis and still be
    // pruned — and it is exactly what a `total > 0` guard would silently drop.
    const zeroed = payload.scores.filter((s) => s.total === 0);
    expect(zeroed.length).toBeGreaterThan(0);

    render(<CritiqueCard data={payload} />);
    const table = screen.getByRole('table');
    expect(within(table).getAllByText('0.0').length).toBeGreaterThanOrEqual(zeroed.length);
    for (const s of zeroed) {
      expect(within(table).getByText(s.perspective)).toBeTruthy();
    }
  });

  it('carries top-k forward, not a single winner', () => {
    // `is_top` is true for more than one position in the captured run. Mapping
    // it as "the winner" would grey out a position the run actually retained.
    expect(payload.scores.filter((s) => s.is_top).length).toBeGreaterThan(1);
  });

  it('renders nothing when there is no critique data', () => {
    const { container } = render(<CritiqueCard data={{ scores: [] }} />);
    expect(container.textContent).toBe('');
  });
});
