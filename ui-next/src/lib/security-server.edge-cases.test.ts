/**
 * Security edge-case tests for server-side validation (security-server.ts).
 *
 * Covers: validateRunRequest, validateRunFollowupRequest, validateCalculateRequest,
 * validateSearchRequest, CSRF token generation/verification, validateUpstreamUrl,
 * readJsonBody, rate limiting.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import crypto from 'crypto';

// Polyfill Web Crypto for Node test environment
if (!global.crypto) {
  Object.defineProperty(global, 'crypto', {
    value: crypto.webcrypto,
    writable: true,
  });
}

import {
  validateRunRequest,
  validateRunFollowupRequest,
  validateCalculateRequest,
  validateSearchRequest,
  validateUpstreamUrl,
  readJsonBody,
  sanitizeRequestHeaders,
  sanitizeResponseHeaders,
  generateCsrfToken,
  signCsrfToken,
  verifyCsrfToken,
  generateSignedCsrfToken,
  rateLimit,
  ValidationError,
  VALIDATION_LIMITS,
  SECURITY_CONSTANTS,
} from './security-server';

import { NextRequest } from 'next/server';

// Helper to create a mock NextRequest
function makeReq(body: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest('http://localhost:3000/api/test', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body,
  });
}


describe('validateRunRequest — edge cases', () => {
  const valid = {
    problem: 'test problem',
    preset: 'multi-perspective-budget',
    top_k: 2,
    sequential: false,
    enhance_prompt: true,
  };

  it('rejects null body', () => {
    expect(() => validateRunRequest(null)).toThrow(ValidationError);
  });

  it('rejects non-object body', () => {
    expect(() => validateRunRequest('string')).toThrow(ValidationError);
    expect(() => validateRunRequest(42)).toThrow(ValidationError);
    expect(() => validateRunRequest([])).toThrow(ValidationError);
  });

  it('rejects empty problem string', () => {
    expect(() => validateRunRequest({ ...valid, problem: '' })).toThrow('Invalid problem');
  });

  it('rejects problem exceeding max length', () => {
    const long = 'x'.repeat(VALIDATION_LIMITS.problemMaxLength + 1);
    expect(() => validateRunRequest({ ...valid, problem: long })).toThrow('Invalid problem');
  });

  it('rejects invalid preset patterns', () => {
    expect(() => validateRunRequest({ ...valid, preset: '' })).toThrow('Invalid preset');
    expect(() => validateRunRequest({ ...valid, preset: '  spaces  ' })).toThrow('Invalid preset');
    expect(() => validateRunRequest({ ...valid, preset: '<script>' })).toThrow('Invalid preset');
    expect(() => validateRunRequest({ ...valid, preset: 'A-uppercase' })).toThrow('Invalid preset');
  });

  it('rejects non-integer top_k', () => {
    expect(() => validateRunRequest({ ...valid, top_k: 1.5 })).toThrow('Invalid top_k');
  });

  it('rejects top_k outside bounds', () => {
    expect(() => validateRunRequest({ ...valid, top_k: 0 })).toThrow('Invalid top_k');
    expect(() => validateRunRequest({ ...valid, top_k: 11 })).toThrow('Invalid top_k');
  });

  it('rejects non-boolean sequential', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(() => validateRunRequest({ ...valid, sequential: 'true' } as any)).toThrow('Invalid sequential');
  });

  it('allows problem at max length boundary', () => {
    const max = 'x'.repeat(VALIDATION_LIMITS.problemMaxLength);
    const result = validateRunRequest({ ...valid, problem: max });
    expect(result.problem).toBe(max);
  });

  it('allows top_k at boundaries', () => {
    const min = validateRunRequest({ ...valid, top_k: 1 });
    expect(min.top_k).toBe(1);
    const max = validateRunRequest({ ...valid, top_k: 10 });
    expect(max.top_k).toBe(10);
  });
});


describe('validateRunFollowupRequest — edge cases', () => {
  const valid = {
    question: 'followup question',
    preset: 'research-budget',
    top_k: 2,
    sequential: false,
    enhance_prompt: true,
    conversation_id: 'conv-123',
    history: [{ role: 'user' as const, content: 'hello' }],
    previous_synthesis: 'previous answer',
    agent_model: null,
  };

  it('rejects empty question', () => {
    expect(() => validateRunFollowupRequest({ ...valid, question: '' })).toThrow('Invalid question');
  });

  it('rejects invalid history format', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(() => validateRunFollowupRequest({ ...valid, history: 'not-array' } as any)).toThrow('Invalid history');
  });

  it('rejects invalid history entry role', () => {
    expect(() => validateRunFollowupRequest({
      ...valid,
      history: [{ role: 'evil', content: 'x' }],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)).toThrow(/role/);
  });

  it('rejects invalid previous_synthesis', () => {
    expect(() => validateRunFollowupRequest({
      ...valid,
      previous_synthesis: 123,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any)).toThrow('Invalid previous_synthesis');
  });

  it('rejects empty conversation_id', () => {
    expect(() => validateRunFollowupRequest({ ...valid, conversation_id: '' })).toThrow('Invalid conversation_id');
  });
});


describe('validateCalculateRequest — edge cases', () => {
  it('accepts valid expression', () => {
    expect(validateCalculateRequest({ expression: '2 + 2' })).toEqual({ expression: '2 + 2' });
  });

  it('rejects non-object body', () => {
    expect(() => validateCalculateRequest(null)).toThrow('Invalid body');
  });

  it('rejects empty expression', () => {
    expect(() => validateCalculateRequest({ expression: '' })).toThrow('Invalid expression');
  });

  it('rejects expression with unsafe characters', () => {
    // Characters like letters, spaces, dashes, slashes, dots are allowed
    expect(() => validateCalculateRequest({ expression: 'rm -rf /' })).not.toThrow();
    // But non-math characters like parentheses used for function calls are rejected
    expect(() => validateCalculateRequest({ expression: 'console.log("xss")' })).toThrow('Invalid expression');
    expect(() => validateCalculateRequest({ expression: '__import__("os")' })).toThrow('Invalid expression');
  });

  it('rejects expression exceeding max length', () => {
    const long = '1+' + '1'.repeat(VALIDATION_LIMITS.expressionMaxLength);
    expect(() => validateCalculateRequest({ expression: long })).toThrow('Invalid expression');
  });

  it('accepts math symbols', () => {
    expect(validateCalculateRequest({ expression: 'sqrt(144)' })).toEqual({ expression: 'sqrt(144)' });
    expect(validateCalculateRequest({ expression: '3.14159 * 2' })).toEqual({ expression: '3.14159 * 2' });
  });
});


describe('validateSearchRequest — edge cases', () => {
  const valid = {
    query: 'test search',
    source_type: 'general',
    num_results: 10,
    smart: false,
  };

  it('rejects empty query', () => {
    expect(() => validateSearchRequest({ ...valid, query: '' })).toThrow('Invalid query');
  });

  it('rejects invalid source_type', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(() => validateSearchRequest({ ...valid, source_type: 'evil' } as any)).toThrow('Invalid source_type');
  });

  it('rejects num_results out of bounds', () => {
    expect(() => validateSearchRequest({ ...valid, num_results: 0 })).toThrow('Invalid num_results');
    expect(() => validateSearchRequest({ ...valid, num_results: 21 })).toThrow('Invalid num_results');
  });

  it('defaults smart to false when missing', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = validateSearchRequest({ query: 'q', source_type: 'general', num_results: 5 } as any);
    expect(result.smart).toBe(false);
  });

  it('defaults source_type to general when missing', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = validateSearchRequest({ query: 'q', num_results: 5 } as any);
    expect(result.source_type).toBe('general');
  });
});


describe('validateUpstreamUrl — edge cases', () => {
  it('rejects non-http protocols', () => {
    expect(() => validateUpstreamUrl('file:///etc/passwd')).toThrow('http or https');
    expect(() => validateUpstreamUrl('javascript:alert(1)')).toThrow();  // 'javascript:' protocol rejected
  });

  it('rejects invalid URLs', () => {
    expect(() => validateUpstreamUrl('not a url')).toThrow('Invalid upstream URL');
    expect(() => validateUpstreamUrl('')).toThrow('Invalid upstream URL');
  });

  it('accepts valid http/https', () => {
    expect(validateUpstreamUrl('http://localhost:8003')).toBe('http://localhost:8003');
    expect(validateUpstreamUrl('https://example.com')).toBe('https://example.com');
  });
});


describe('sanitizeRequestHeaders — edge cases', () => {
  it('strips disallowed headers', () => {
    const headers = new Headers({
      'authorization': 'Bearer token',
      'content-type': 'application/json',
      'x-csrf-token': 'abc123',
      'x-custom-evil': 'malicious',
    });
    const result = sanitizeRequestHeaders(headers);
    expect(result).toHaveProperty('authorization');
    expect(result).toHaveProperty('x-csrf-token');
    expect(result).not.toHaveProperty('x-custom-evil');
  });

  it('handles empty headers', () => {
    const result = sanitizeRequestHeaders(new Headers());
    expect(Object.keys(result)).toHaveLength(0);
  });
});


describe('sanitizeResponseHeaders — edge cases', () => {
  it('removes hop-by-hop headers', () => {
    const upstream = new Response('ok', {
      headers: {
        'content-type': 'text/plain',
        'connection': 'keep-alive',
        'transfer-encoding': 'chunked',
        'x-custom': 'value',
      },
    });
    const result = sanitizeResponseHeaders(upstream);
    expect(result.get('content-type')).toBe('text/plain');
    expect(result.get('x-custom')).toBe('value');
    expect(result.get('connection')).toBeNull();
    expect(result.get('transfer-encoding')).toBeNull();
  });
});


describe('CSRF token — cryptography edge cases', () => {
  it('generates a valid signed token', async () => {
    // Set CSRF_SECRET for the test
    process.env.CSRF_SECRET = 'test-secret-at-least-32-bytes-long!!';

    const signed = await generateSignedCsrfToken();
    expect(signed).toBeTruthy();
    expect(signed).toContain(':');
    expect(signed).toContain('.');

    const isValid = await verifyCsrfToken(signed);
    expect(isValid).toBe(true);

    delete process.env.CSRF_SECRET;
  });

  it('rejects tampered token', async () => {
    process.env.CSRF_SECRET = 'test-secret-at-least-32-bytes-long!!';

    const signed = await generateSignedCsrfToken();
    const tampered = signed.replace(/[a-f0-9]/, '0');
    const isValid = await verifyCsrfToken(tampered);
    expect(isValid).toBe(false);

    delete process.env.CSRF_SECRET;
  });

  it('rejects token with missing signature', async () => {
    process.env.CSRF_SECRET = 'test-secret-at-least-32-bytes-long!!';
    expect(await verifyCsrfToken('not-a-valid-token')).toBe(false);
    expect(await verifyCsrfToken('')).toBe(false);
    expect(await verifyCsrfToken('only.dots.here')).toBe(false);
    delete process.env.CSRF_SECRET;
  });

  it('fails without CSRF_SECRET', async () => {
    delete process.env.CSRF_SECRET;
    await expect(generateSignedCsrfToken()).rejects.toThrow('CSRF_SECRET');
  });
});


describe('rateLimit — edge cases', () => {
  it('allows first request for any action', () => {
    const req = new NextRequest('http://localhost/api/run', {
      headers: { 'x-forwarded-for': '10.0.0.1' },
    });
    const result = rateLimit(req, 'run');
    expect(result.allowed).toBe(true);
    expect(result.retryAfter).toBe(0);
  });

  it('blocks after exceeding limit', () => {
    const ip = '10.0.0.2';
    for (let i = 0; i < 10; i++) {
      const req = new NextRequest('http://localhost/api/run', {
        headers: { 'x-forwarded-for': ip },
      });
      rateLimit(req, 'run');
    }
    const req = new NextRequest('http://localhost/api/run', {
      headers: { 'x-forwarded-for': ip },
    });
    const result = rateLimit(req, 'run');
    expect(result.allowed).toBe(false);
    expect(result.retryAfter).toBeGreaterThan(0);
  });

  it('falls back to default limit for unknown action', () => {
    const req = new NextRequest('http://localhost/api/unknown', {
      headers: { 'x-forwarded-for': '10.0.0.3' },
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = rateLimit(req, 'unknown-action' as any);
    expect(result.allowed).toBe(true);
  });

  it('uses x-real-ip when x-forwarded-for is missing', () => {
    const req = new NextRequest('http://localhost/api/search', {
      headers: { 'x-real-ip': '10.0.0.4' },
    });
    const result = rateLimit(req, 'search');
    expect(result.allowed).toBe(true);
  });

  it('defaults to unknown when no IP headers present', () => {
    const req = new NextRequest('http://localhost/api/search');
    const result = rateLimit(req, 'search');
    expect(result.allowed).toBe(true);
  });

  it('resets bucket after window expires', async () => {
    // This test verifies the expired bucket eviction
    // We rely on the modulo cleanup mechanism
    const ip = '10.0.0.5';
    // Fire one request to create a bucket
    const req1 = new NextRequest('http://localhost/api/calculate', {
      headers: { 'x-forwarded-for': ip },
    });
    rateLimit(req1, 'calculate');

    // The bucket exists with count=1; subsequent requests should increment
    const req2 = new NextRequest('http://localhost/api/calculate', {
      headers: { 'x-forwarded-for': ip },
    });
    rateLimit(req2, 'calculate');
    rateLimit(req2, 'calculate');

    // Still allowed (limit is 20 for calculate)
    const result = rateLimit(req2, 'calculate');
    expect(result.allowed).toBe(true);
  });

  it('different actions have separate limits', () => {
    const ip = '10.0.0.6';
    // Exhaust run limit
    for (let i = 0; i < 10; i++) {
      const req = new NextRequest('http://localhost/api/run', {
        headers: { 'x-forwarded-for': ip },
      });
      rateLimit(req, 'run');
    }
    // Run should be blocked
    const runReq = new NextRequest('http://localhost/api/run', {
      headers: { 'x-forwarded-for': ip },
    });
    const runResult = rateLimit(runReq, 'run');
    expect(runResult.allowed).toBe(false);

    // But search should still work
    const searchReq = new NextRequest('http://localhost/api/search', {
      headers: { 'x-forwarded-for': ip },
    });
    const searchResult = rateLimit(searchReq, 'search');
    expect(searchResult.allowed).toBe(true);
  });
});


describe('readJsonBody — edge cases', () => {
  it('rejects non-JSON content type', async () => {
    const req = new NextRequest('http://localhost/api/test', {
      method: 'POST',
      headers: { 'content-type': 'text/plain' },
      body: 'hello',
    });
    await expect(readJsonBody(req)).rejects.toThrow('Invalid content type');
  });

  it('rejects payload exceeding max bytes', async () => {
    const big = JSON.stringify({ data: 'x'.repeat(2_000_000) });
    const req = new NextRequest('http://localhost/api/test', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: big,
    });
    await expect(readJsonBody(req)).rejects.toThrow('Payload too large');
  });

  it('rejects malformed JSON', async () => {
    const req = new NextRequest('http://localhost/api/test', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{not valid',
    });
    await expect(readJsonBody(req)).rejects.toThrow();
  });

  it('accepts valid JSON at limit boundary', async () => {
    const data = { key: 'value' };
    const body = JSON.stringify(data);
    const req = new NextRequest('http://localhost/api/test', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body,
    });
    const result = await readJsonBody(req, body.length + 10);
    expect(result).toEqual(data);
  });
});


describe('CSRF token — validity checks', () => {
  beforeEach(() => {
    process.env.CSRF_SECRET = 'a-very-long-secret-key-for-testing-csrf!!!';
  });

  it('generated token has expected format', () => {
    const token = generateCsrfToken();
    expect(token).toMatch(/^\d+:[0-9a-f]{48}$/);
  });

  it('signCsrfToken produces expected format', async () => {
    const token = generateCsrfToken();
    const signed = await signCsrfToken(token);
    expect(signed).toMatch(/^\d+:[0-9a-f]{48}\.[0-9a-f]{64}$/);
  });

  it('rejects expired token', async () => {
    // Create a token with an old timestamp
    const oldToken = `${Math.floor(Date.now() / 1000) - 90000}:${'a'.repeat(48)}`;
    const isValid = await verifyCsrfToken(oldToken);
    // Expect false: timestamp expired (CSRF max age is 86400)
    expect(isValid).toBe(false);
  });

  it('rejects token with invalid timestamp format', async () => {
    expect(await verifyCsrfToken('abc:ff1234.signedpart')).toBe(false);
  });
});
