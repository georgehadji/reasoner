// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

const mocked = vi.hoisted(() => ({ submitContact: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ submitContact: mocked.submitContact }));
vi.mock('@/components/layout/SiteHeader', () => ({ SiteHeader: () => null }));
vi.mock('@/components/layout/SiteFooter', () => ({ SiteFooter: () => null }));

import ContactPage from './page';

function fillAndSend() {
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ada Lovelace' } });
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ada@example.com' } });
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Scope a pilot.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
}

beforeEach(() => {
  mocked.submitContact.mockReset();
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '', '/');
});

describe('contact form', () => {
  it('shows success only after the request succeeds', async () => {
    mocked.submitContact.mockResolvedValue({ status: 'sent' });
    render(<ContactPage />);
    fillAndSend();
    expect(await screen.findByRole('heading', { name: 'Message sent.' })).toBeTruthy();
    expect(mocked.submitContact).toHaveBeenCalledWith({
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      subject: 'Billing Issue',
      message: 'Scope a pilot.',
    });
  });

  it('keeps the form and shows an error when the request fails', async () => {
    mocked.submitContact.mockRejectedValue(new Error('HTTP 503'));
    render(<ContactPage />);
    fillAndSend();
    expect(await screen.findByText(/your message was not sent/i)).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Message sent.' })).toBeNull();
    expect((screen.getByLabelText('Message') as HTMLTextAreaElement).value).toBe('Scope a pilot.');
  });

  it('preselects the Pilot topic from ?topic=pilot', () => {
    window.history.replaceState(null, '', '/contact?topic=pilot');
    render(<ContactPage />);
    expect((screen.getByLabelText('Topic') as HTMLSelectElement).value).toBe('Pilot');
  });
});
