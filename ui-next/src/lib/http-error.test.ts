import { describe, expect, it } from 'vitest';
import { describeHttpError, formatRetryAfter } from './http-error';

describe('describeHttpError', () => {
  // A 429 used to reach the chat as the whole JSON payload.
  it('turns a rate-limit body into one line with the retry time', () => {
    const body = JSON.stringify({
      error: 'Free trial usage for this address is exhausted for today.',
      status_code: 429,
      detail: { error: 'Anonymous trial limit reached', message: 'Free trial usage…', retry_after: 86400 },
    });
    expect(describeHttpError(429, body)).toBe('Anonymous trial limit reached. Try again in 24 hours.');
  });

  it('uses the Retry-After header when the body has no retry_after', () => {
    expect(describeHttpError(429, JSON.stringify({ error: 'Too many requests' }), '90')).toBe(
      'Too many requests. Try again in 2 minutes.',
    );
  });

  it('shows the server message for other errors', () => {
    expect(describeHttpError(402, JSON.stringify({ error: 'Not enough credits' }))).toBe('Not enough credits');
  });

  it('falls back to the status when the body is not JSON', () => {
    expect(describeHttpError(500, '<html>oops</html>')).toBe('Request failed (HTTP 500).');
  });
});

describe('formatRetryAfter', () => {
  it.each([
    [30, '30 seconds'],
    [60, '1 minute'],
    [3600, '1 hour'],
    [86400, '24 hours'],
  ])('%i s -> %s', (seconds, text) => {
    expect(formatRetryAfter(seconds)).toBe(text);
  });
});

describe('describeHttpError: unverified email', () => {
  const confirm = 'Confirm your email to unlock your free credits and API keys. Check your inbox for the link.';

  it('a 402 marked email_unverified asks for the confirmation, not money', () => {
    const body = JSON.stringify({ error: 'Insufficient credits', detail: { email_unverified: true, upgrade_url: '/pricing' } });
    expect(describeHttpError(402, body)).toBe(confirm);
  });

  it('a 403 with code email_unverified asks for the confirmation', () => {
    const body = JSON.stringify({ error: 'Confirm your email address before creating an API key.', detail: { code: 'email_unverified' } });
    expect(describeHttpError(403, body)).toBe(confirm);
  });

  it('a plain 402 keeps the server message', () => {
    const body = JSON.stringify({ error: 'Insufficient credits', detail: { upgrade_url: '/pricing' } });
    expect(describeHttpError(402, body)).toBe('Insufficient credits');
  });
});
