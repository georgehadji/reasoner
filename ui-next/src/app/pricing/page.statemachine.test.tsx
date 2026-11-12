// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';

/** SM-U7: two rapid checkout clicks. The guard is `disabled={!!loadingTier}`. */
const mocked = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ apiFetch: mocked.apiFetch }));
vi.mock('@/components/layout/SiteHeader', () => ({ SiteHeader: () => null }));
vi.mock('@/components/layout/SiteFooter', () => ({ SiteFooter: () => null }));

import PricingPage from './page';

beforeEach(() => {
  cleanup();
  mocked.apiFetch.mockReset();
  mocked.apiFetch.mockImplementation(() => new Promise(() => {})); // checkout in flight
});

describe('SM-U7 pricing checkout', () => {
  it('SM-U7: a second click while checkout is in flight starts no second checkout', () => {
    render(<PricingPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Upgrade' }));
    const stripe = screen.getByRole('button', { name: /pay with card/i });
    fireEvent.click(stripe);
    fireEvent.click(stripe);
    expect(mocked.apiFetch).toHaveBeenCalledTimes(1);
  });

  it('SM-U7: the other provider button is also locked while one checkout is in flight', () => {
    render(<PricingPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Upgrade' }));
    const stripe = screen.getByRole('button', { name: /pay with card/i });
    const paypal = screen.getByRole('button', { name: /paypal/i });
    fireEvent.click(stripe);
    fireEvent.click(paypal);
    expect(mocked.apiFetch).toHaveBeenCalledTimes(1);
  });

  it('SM-U7: a bfcache restore clears the frozen pending spinner', () => {
    render(<PricingPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Upgrade' }));
    const stripe = screen.getByRole('button', { name: /pay with card/i });
    fireEvent.click(stripe);
    expect(stripe).toBeDisabled();
    act(() => {
      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    });
    expect(screen.getByRole('button', { name: /pay with card/i })).toBeEnabled();
  });
});
