// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { QualityChip } from './PhaseCard';

describe('QualityChip', () => {
  // A clean rule pass is structural, not a grade. It used to arrive as a
  // constant 8.0, so every article phase read "Quality 8.0/10" (2026-11-09).
  it('shows "Checks passed" and no number when the phase was not graded', () => {
    render(<QualityChip quality={{ score: null, passed: true }} />);

    expect(screen.getByText(/checks passed/i)).toBeInTheDocument();
    expect(screen.queryByText(/\/10/)).toBeNull();
  });

  it('shows the grade when something measured one', () => {
    render(<QualityChip quality={{ score: 6, passed: true }} />);

    expect(screen.getByText('6.0/10')).toBeInTheDocument();
  });
});
