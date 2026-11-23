// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DashboardView, type DashboardViewProps } from './DashboardView';

const credits = (balance: number) => ({
  balance,
  balance_usd: balance / 1000,
  lifetime_granted: 500,
  lifetime_spent: 500 - balance,
  tier: 'free',
  monthly_allowance: 500,
  credits_per_usd: 1000,
  updated_at: '2026-11-14T00:00:00Z',
});

const props = (over: Partial<DashboardViewProps> = {}): DashboardViewProps => ({
  credits: credits(410),
  ledger: [],
  creditsStatus: 'ok',
  onRetryCredits: vi.fn(),
  quota: { used: 6, max: 20, remaining: 14, reset_date: '2026-12-01T00:00:00+00:00' },
  quotaStatus: 'ok',
  tier: 'free',
  planLoading: false,
  onManageBilling: vi.fn(),
  portalError: '',
  ...over,
});

describe('DashboardView', () => {
  it('reads the balance as budget runs in the title line', () => {
    render(<DashboardView {...props()} />);
    expect(screen.getByText('410 credits left: about 20 budget runs.')).toBeTruthy();
  });

  it('offers a top-up, not a run count, at zero', () => {
    render(<DashboardView {...props({ credits: credits(0) })} />);
    expect(screen.getByText(/No credits left/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Top up' }).getAttribute('href')).toBe('/pricing');
  });

  it('says the balance failed to load and offers a retry', () => {
    const onRetryCredits = vi.fn();
    render(<DashboardView {...props({ credits: null, creditsStatus: 'error', onRetryCredits })} />);
    screen.getByRole('button', { name: 'Try again' }).click();
    expect(onRetryCredits).toHaveBeenCalledOnce();
  });

  it('signs every ledger change', () => {
    const ledger = [
      { id: 'b', delta: -20, balance_after: 480, reason: 'pipeline_run', description: null, created_at: '2026-11-03T09:14:00Z' },
      { id: 'a', delta: 500, balance_after: 500, reason: 'monthly_grant', description: null, created_at: '2026-11-01T00:00:00Z' },
    ];
    render(<DashboardView {...props({ ledger })} />);
    expect(screen.getByText('−20')).toBeTruthy();
    expect(screen.getByText('+500')).toBeTruthy();
    expect(screen.getByText('Monthly allowance')).toBeTruthy();
  });

  it('shows Manage billing only on a paid plan', () => {
    const { rerender } = render(<DashboardView {...props()} />);
    expect(screen.queryByRole('button', { name: 'Manage billing' })).toBeNull();
    rerender(<DashboardView {...props({ tier: 'pro' })} />);
    expect(screen.getByRole('button', { name: 'Manage billing' })).toBeTruthy();
  });
});
