// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

vi.mock('@/lib/auth', () => ({ resendConfirmation: vi.fn() }));

import { resendConfirmation } from '@/lib/auth';
import { useAppStore } from '@/stores/app-store';
import { EmailVerifyBanner } from './EmailVerifyBanner';

const resend = resendConfirmation as ReturnType<typeof vi.fn>;
const signIn = (confirmed: string | null) =>
  useAppStore.setState({
    user: { id: 'u', email: 'a@b.c', email_confirmed_at: confirmed ?? undefined } as never,
  });

describe('EmailVerifyBanner', () => {
  beforeEach(() => {
    resend.mockReset();
  });

  it('shows nothing for a confirmed address', () => {
    signIn('2026-01-01T00:00:00Z');
    const { container } = render(<EmailVerifyBanner />);
    expect(container.textContent).toBe('');
  });

  it('shows nothing when signed out', () => {
    useAppStore.setState({ user: null });
    const { container } = render(<EmailVerifyBanner />);
    expect(container.textContent).toBe('');
  });

  it('asks an unconfirmed user to confirm, and a double click sends one link', async () => {
    signIn(null);
    let settle: () => void = () => {};
    resend.mockReturnValue(new Promise<void>((r) => { settle = r; }));
    render(<EmailVerifyBanner />);
    expect(screen.getByRole('status').textContent).toContain('Confirm a@b.c');
    const button = screen.getByRole('button', { name: 'Resend link' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(resend).toHaveBeenCalledTimes(1);
    await act(async () => settle());
    expect(screen.getByRole('status').textContent).toContain('Link sent to a@b.c');
  });

  it('shows the error when the resend fails', async () => {
    signIn(null);
    resend.mockRejectedValue(new Error('Too many requests'));
    render(<EmailVerifyBanner />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Resend link' }));
    });
    expect(screen.getByRole('alert').textContent).toContain('Too many requests');
  });
});
