import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReliabilityBanner, ScopeLine, scopeLine } from './ReliabilityBanner';

describe('ReliabilityBanner', () => {
  it('renders nothing for "answer" and for an empty report', () => {
    const a = render(<ReliabilityBanner reliability={{ level: 'answer', reasons: [] }} />);
    expect(a.container.innerHTML).toBe('');
    const b = render(<ReliabilityBanner reliability={{}} />);
    expect(b.container.innerHTML).toBe('');
  });

  it('shows a caution note with reasons for answer_with_caveats', () => {
    render(<ReliabilityBanner reliability={{ level: 'answer_with_caveats', reasons: ['Sources disagree'] }} />);
    expect(screen.getByRole('note').textContent).toMatch(/Use with caution/);
    expect(screen.getByText('Sources disagree')).toBeTruthy();
  });

  it('shows a stronger alert for refer', () => {
    render(<ReliabilityBanner reliability={{ level: 'refer', reasons: ['No authoritative source found'] }} />);
    expect(screen.getByRole('alert').textContent).toMatch(/Check with a professional/);
    expect(screen.getByText('No authoritative source found')).toBeTruthy();
  });
});

describe('scope line', () => {
  it('maps known codes and falls back to the code', () => {
    expect(scopeLine({ jurisdiction: 'GR', as_of: '2026-11-14' })).toBe('Scope: Greece · as of 2026-11-14');
    expect(scopeLine({ jurisdiction: 'JP', as_of: '2026-11-14' })).toBe('Scope: JP · as of 2026-11-14');
  });
  it('says country not stated when jurisdiction is null', () => {
    render(<ScopeLine scope={{ jurisdiction: null, as_of: '2026-11-14' }} />);
    expect(screen.getByText('Scope: country not stated · as of 2026-11-14')).toBeTruthy();
  });
  it('is absent for an empty scope', () => {
    expect(scopeLine({})).toBeNull();
    expect(scopeLine(undefined)).toBeNull();
  });
});
