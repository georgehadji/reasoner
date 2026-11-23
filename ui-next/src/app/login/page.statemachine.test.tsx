// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

/** SM-U8: one pending action across the email form and the OAuth buttons. */
const auth = vi.hoisted(() => ({ signInWithEmail: vi.fn(), signInWithOAuth: vi.fn() }));
vi.mock('@/lib/auth', () => ({
  signInWithEmail: auth.signInWithEmail,
  signInWithOAuth: auth.signInWithOAuth,
  getEnabledOAuthProviders: () => ['google'],
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/login',
}));

import LoginPage from './page';

beforeEach(() => {
  cleanup();
  auth.signInWithEmail.mockReset();
  auth.signInWithOAuth.mockReset();
});

function fill() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.co' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret1' } });
}

describe('SM-U8 login', () => {
  it('SM-U8: while email sign-in is pending the OAuth button is locked and starts nothing', () => {
    auth.signInWithEmail.mockImplementation(() => new Promise(() => {}));
    render(<LoginPage />);
    fill();
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    const google = screen.getByRole('button', { name: /google/i });
    expect(google).toBeDisabled();
    fireEvent.click(google);
    expect(auth.signInWithOAuth).not.toHaveBeenCalled();
  });

  it('SM-U8: a rejected sign-in shows the error and a retry is allowed', async () => {
    auth.signInWithEmail.mockRejectedValueOnce({ message: 'Bad credentials' });
    render(<LoginPage />);
    fill();
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Bad credentials');
    auth.signInWithEmail.mockResolvedValueOnce(undefined);
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(auth.signInWithEmail).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });
});
