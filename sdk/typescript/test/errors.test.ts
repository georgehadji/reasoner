import { describe, expect, test } from 'vitest';
import {
  AuthenticationError,
  BadRequestError,
  DuplicateRunError,
  InsufficientCreditsError,
  PermissionError,
  RateLimitError,
  ReasonerError,
  ServerError,
  errorFromResponse,
  formatApiError,
  parseRetryAfter,
} from '../src/errors.js';

function raise(status: number, body: unknown, headers: Record<string, string> = {}) {
  return errorFromResponse(status, JSON.stringify(body), new Headers(headers), 'run-1');
}

describe('formatApiError', () => {
  test('flattens FastAPI validation detail arrays', () => {
    const message = formatApiError(400, {
      detail: [{ loc: ['body', 'problem'], msg: 'Problem cannot be empty' }],
    });
    expect(message).toBe('HTTP 400: problem: Problem cannot be empty');
  });

  test('joins multiple validation failures', () => {
    const message = formatApiError(400, {
      detail: [
        { loc: ['body', 'problem'], msg: 'too long' },
        { loc: ['body', 'preset'], msg: 'Invalid preset' },
      ],
    });
    expect(message).toBe('HTTP 400: problem: too long; preset: Invalid preset');
  });

  test('reads a plain string detail', () => {
    expect(formatApiError(409, { detail: 'Run x is already in progress' })).toBe(
      'HTTP 409: Run x is already in progress',
    );
  });

  test('reads the nested error on a rate-limit body', () => {
    expect(formatApiError(429, { detail: { error: 'Rate limit exceeded', retry_after: 60 } })).toBe(
      'HTTP 429: Rate limit exceeded',
    );
  });

  test('falls back to the bare status for unrecognised bodies', () => {
    expect(formatApiError(500, 'not an object')).toBe('HTTP 500');
  });
});

describe('parseRetryAfter', () => {
  test('reads a delay in seconds', () => {
    expect(parseRetryAfter('30')).toBe(30_000);
  });

  test('reads an HTTP date', () => {
    const future = new Date(Date.now() + 5_000).toUTCString();
    const ms = parseRetryAfter(future);
    expect(ms).toBeGreaterThan(3_000);
    expect(ms).toBeLessThanOrEqual(6_000);
  });

  test('returns undefined when absent or unparseable', () => {
    expect(parseRetryAfter(null)).toBeUndefined();
    expect(parseRetryAfter('soon')).toBeUndefined();
  });
});

describe('errorFromResponse', () => {
  test('maps each documented status to its class', () => {
    expect(raise(400, {})).toBeInstanceOf(BadRequestError);
    expect(raise(401, {})).toBeInstanceOf(AuthenticationError);
    expect(raise(402, {})).toBeInstanceOf(InsufficientCreditsError);
    expect(raise(403, {})).toBeInstanceOf(PermissionError);
    expect(raise(409, {})).toBeInstanceOf(DuplicateRunError);
    expect(raise(429, {})).toBeInstanceOf(RateLimitError);
    expect(raise(503, {})).toBeInstanceOf(ServerError);
  });

  test('maps 422 to a bad request, since FastAPI validates with it', () => {
    expect(raise(422, {})).toBeInstanceOf(BadRequestError);
  });

  test('attaches the colliding run id to a duplicate error', () => {
    const error = raise(409, { detail: 'Run run-1 is already in progress' });
    expect((error as DuplicateRunError).clientRunId).toBe('run-1');
  });

  test('attaches Retry-After to a rate-limit error', () => {
    const error = raise(429, {}, { 'Retry-After': '12' });
    expect((error as RateLimitError).retryAfterMs).toBe(12_000);
  });

  test('keeps an unmapped 4xx as the base error', () => {
    const error = raise(418, {});
    expect(error).toBeInstanceOf(ReasonerError);
    expect(error).not.toBeInstanceOf(BadRequestError);
  });

  test('survives a non-JSON body', () => {
    const error = errorFromResponse(502, '<html>bad gateway</html>', new Headers());
    expect(error).toBeInstanceOf(ServerError);
    expect(error.message).toBe('HTTP 502');
    expect(error.body).toBe('<html>bad gateway</html>');
  });

  test('exposes the parsed body for programmatic inspection', () => {
    const error = raise(402, { detail: 'Credit balance exhausted' });
    expect(error.data).toEqual({ detail: 'Credit balance exhausted' });
  });
});
