// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('@/hooks/useQuota', () => ({ useQuota: vi.fn() }));

import { useQuota } from '@/hooks/useQuota';
import { UsageBadge } from './UsageBadge';

const mockQuota = (quota: unknown) =>
  (useQuota as ReturnType<typeof vi.fn>).mockReturnValue({ quota, loading: false, refresh: vi.fn() });

describe('UsageBadge', () => {
  it('renders used / max for a limited plan', () => {
    mockQuota({ used: 5, max: 20, remaining: 15, reset_date: '2026-11-01' });
    render(<UsageBadge />);
    expect(screen.getByText('5 / 20 queries')).toBeTruthy();
  });

  // Regression: the backend used to send max: -1 for ENTERPRISE, which rendered
  // "0 / -1 queries" (and a negative percentage).
  it('renders Unlimited, not a numeric cap, on an unlimited plan', () => {
    mockQuota({ used: 0, max: null, unlimited: true, remaining: -1, reset_date: '2026-11-01' });
    const { container } = render(<UsageBadge />);
    expect(screen.getByText('Unlimited queries')).toBeTruthy();
    expect(container.textContent).not.toContain('-1');
  });

  it('renders nothing until quota has loaded', () => {
    mockQuota(null);
    const { container } = render(<UsageBadge />);
    expect(container.textContent).toBe('');
  });
});
