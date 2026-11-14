import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RunProgress } from './RunProgress';

describe('RunProgress', () => {
  it('names no method and draws no placeholder boxes before the method is known', () => {
    render(<RunProgress phases={[]} startedAt={Date.now()} />);
    expect(screen.getByText('Choosing a method…')).toBeTruthy();
    expect(screen.getByText('Reading your question…')).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });

  it('shows the step, the running phase and what comes next', () => {
    render(
      <RunProgress
        method="pre_mortem"
        phases={[{ index: 0, phase: 1.5, name: 'Case Study Research', data: {} }]}
        currentPhase={2}
        currentPhaseName="Failure Narrative"
      />,
    );
    expect(screen.getByText('Pre-Mortem')).toBeTruthy();
    expect(screen.getByText(/step 2 of 6/)).toBeTruthy();
    expect(screen.getByText('Failure Narrative…')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1');
    expect(screen.getByText(/^Next: /)).toBeTruthy();
  });

  it('drops plan phases the run skipped from the count and from Next', () => {
    render(
      <RunProgress
        method="multi_perspective"
        phases={[{ index: 0, phase: 2, name: 'Perspectives', data: {} }]}
        currentPhase={3}
        currentPhaseName="Critique & Pruning"
      />,
    );
    expect(screen.getByText(/step 2 of 4/)).toBeTruthy();
    expect(screen.getByText(/^Next: /).textContent).toBe('Next: Stress Testing · Synthesis');
  });

  it('keeps a finished synthesis to one closed row inside the card', () => {
    render(
      <RunProgress
        method="debate"
        phases={[{ index: 0, phase: 5, name: 'Synthesis', data: { core_solution: 'Ban cars in phases.', action_blueprint: [] } }]}
      />,
    );
    expect(screen.getByRole('button', { expanded: false })).toBeTruthy();
    expect(screen.queryByText('Synthesis Highlights')).toBeNull();
  });
});
