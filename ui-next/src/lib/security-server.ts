import { NextRequest, NextResponse } from 'next/server';
import { CSRF_HEADER } from './security-constants';
import { RunRequest } from './types';
import { REASONER_API_BASE } from './server-config';
import { TIMING } from './config';

// Turbopack cache-bust hash — changing this forces a recompile of routes that import it.
export const SECURITY_SERVER_HASH = 'v1-8004';

export const VALIDATION_LIMITS = {
  problemMaxLength: 10000,
  questionMaxLength: 10000,
  expressionMaxLength: 1000,
  queryMaxLength: 500,
  topKMin: 1,
  topKMax: 10,
  numResultsMin: 1,
  numResultsMax: 20,
};

export const SECURITY_CONSTANTS = {
  allowedPorts: new Set(['', '80', '443', '8000', '8003', '8004', '8080', '3000']),
  rateLimitWindowMs: 60_000,
  rateLimitMaxEntries: 10_000,
  rateLimitEvictionBatch: 100,
  rateLimitCleanupModulo: 100,
};

// Tokens use the backend's format (src/reasoner/api/csrf.py), so the cookie this
// proxy mints is one the backend also accepts. Without Caddy the proxy's token
// is the X-CSRF-Token the backend verifies; the old `ts:rand` shape failed there
// and every proxied POST was a 403 with backend CSRF enforcement on.
// tests/test_csrf_token_parity.py pins the shared vector.
const PAYLOAD_SIG_HEX_CHARS = 16;

function toHex(bytes: ArrayBuffer | Uint8Array): string {
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function hmacHex(message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    await getCsrfSecret(),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  return toHex(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message)));
}

/** `expiry:nonce:sig16`, where sig16 binds the expiry so it cannot be edited. */
export async function buildCsrfToken(expiry: number, nonce: string): Promise<string> {
  const payload = `${expiry}:${nonce}`;
  const sig = (await hmacHex(payload)).slice(0, PAYLOAD_SIG_HEX_CHARS);
  return `${payload}:${sig}`;
}

export async function generateCsrfToken(): Promise<string> {
  const nonce = new Uint8Array(16);
  crypto.getRandomValues(nonce);
  const expiry = Math.floor(Date.now() / 1000) + TIMING.csrfMaxAgeSeconds;
  return buildCsrfToken(expiry, toHex(nonce));
}

async function getCsrfSecret(): Promise<ArrayBuffer> {
  const raw = process.env.CSRF_SECRET;
  if (!raw) {
    throw new Error(
      'CSRF_SECRET must be set in the server environment. ' +
      'It must be a cryptographically random string of at least 32 bytes. ' +
      'Do not reuse API_BASE_URL or any predictable value.'
    );
  }
  const enc = new TextEncoder().encode(raw);
  return crypto.subtle.digest('SHA-256', enc);
}

export async function signCsrfToken(token: string): Promise<string> {
  return `${token}.${await hmacHex(token)}`;
}

export async function verifyCsrfToken(signed: string): Promise<boolean> {
  const idx = signed.lastIndexOf('.');
  if (idx === -1) return false;
  const token = signed.slice(0, idx);

  // expiry:nonce:sig16, the backend's shape. The embedded expiry is checked
  // against its own signature, as verify_csrf_token does.
  const parts = token.split(':');
  if (parts.length !== 3) return false;
  const expiry = parseInt(parts[0], 10);
  if (!Number.isFinite(expiry) || Date.now() / 1000 >= expiry) return false;

  const expectedToken = await buildCsrfToken(expiry, parts[1]);
  const expected = `${expectedToken}.${await hmacHex(expectedToken)}`;
  if (expected.length !== signed.length) return false;
  let result = 0;
  for (let i = 0; i < signed.length; i++) {
    result |= signed.charCodeAt(i) ^ expected.charCodeAt(i);
  }
  return result === 0;
}

export async function requireCsrfToken(req: NextRequest): Promise<void> {
  const token = req.headers.get(CSRF_HEADER);
  if (!token) throw new ValidationError('Missing CSRF token');
  const valid = await verifyCsrfToken(token);
  if (!valid) throw new ValidationError('Invalid CSRF token');
}

export async function generateSignedCsrfToken(): Promise<string> {
  return signCsrfToken(await generateCsrfToken());
}

/**
 * Extract a bearer token from the Authorization header, or null.
 *
 * Agent routes are bearer-only — no CSRF token, no session cookie. Without
 * this check a proxy route would forward a CSRF-free, credential-free
 * request straight to a metered backend endpoint that requires one of the
 * two; failing here, in the proxy, is cheaper than round-tripping to find
 * out the same thing from a 401.
 */
export function extractBearerToken(req: NextRequest): string | null {
  const header = req.headers.get('authorization') ?? '';
  return header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() || null : null;
}

export function getApiBaseUrl(): string {
  if (process.env.API_BASE_URL) return process.env.API_BASE_URL;
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    if (process.env.NODE_ENV === 'production') {
      throw new Error('API_BASE_URL must be configured server-side in production');
    }
    console.warn('SECURITY: Using NEXT_PUBLIC_API_BASE_URL. Prefer API_BASE_URL (server-only).');
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  if (process.env.NODE_ENV === 'production') {
    throw new Error('API_BASE_URL must be configured in production');
  }
  return REASONER_API_BASE;
}

export function validateUpstreamUrl(url: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error('Invalid upstream URL');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('Upstream URL must use http or https');
  }

  const allowedPorts = SECURITY_CONSTANTS.allowedPorts;
  const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
  if (!allowedPorts.has(port)) {
    throw new Error('Upstream URL uses a disallowed port');
  }

  if (process.env.NODE_ENV === 'production') {
    /* WHATWG URL keeps the brackets on an IPv6 literal: `new URL('http://[::1]/')`
       has hostname `"[::1]"`, not `"::1"`. Every IPv6 arm below was written
       against the unbracketed form, so none of them could ever match and the
       whole IPv6 half of this guard was dead — `::1`, `::`, the unique-local
       range and the link-local range were all reachable upstream targets in
       production. Strip the brackets once, here, and lowercase so the hex
       comparisons below do not depend on how the caller cased the address. */
    const hostname = parsed.hostname.replace(/^\[|\]$/g, '').toLowerCase();

    if (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '::1' ||
      hostname === '0.0.0.0' ||
      hostname === '::' ||
      hostname === '169.254.169.254' ||
      hostname === 'metadata.google.internal' ||
      hostname.startsWith('192.168.') ||
      hostname.startsWith('10.') ||
      hostname.startsWith('169.254.') ||
      /^127\./.test(hostname) ||
      /^172\.(1[6-9]|2\d|3[01])\./.test(hostname) ||
      /* Unique-local is fc00::/7 — the top seven bits, which means a leading
         byte of either `fc` or `fd`. The old `fc[0-9a-f]{2}` covered only half
         the range and would have missed every `fd..` address even with the
         brackets stripped; `fd00::/8` is the half actually used in practice,
         since fc00::/8 is unassigned. */
      /^f[cd][0-9a-f]{2}:/.test(hostname) ||
      /* Link-local fe80::/10. */
      /^fe[89ab][0-9a-f]:/.test(hostname) ||
      /* Deprecated site-local fec0::/10 — still routed by some stacks. */
      /^fe[cdef][0-9a-f]:/.test(hostname) ||
      /* IPv4-mapped (::ffff:0:0/96). Node normalises the embedded address to
         hex — `::ffff:127.0.0.1` arrives as `::ffff:7f00:1` — so decoding it
         back to a dotted quad to re-run the checks above would be the only way
         to filter these individually. Nothing legitimate configures an upstream
         as an IPv4-mapped literal, so the whole range goes. */
      hostname.startsWith('::ffff:')
    ) {
      throw new Error('Upstream URL points to a private network in production');
    }
  }
  return url;
}

/**
 * Shared secret for the FastAPI /api/neuro/* gate, forwarded by the neuro
 * proxy routes. Must match NEURO_INTERNAL_KEY on the API workers.
 *
 * Server-only: never read this through NEXT_PUBLIC_, and note it is
 * deliberately absent from sanitizeRequestHeaders' allowlist below so a
 * browser cannot supply its own. Empty when unset, which is the local-dev
 * posture where the backend leaves the endpoints ungated.
 */
export function neuroKeyHeader(): Record<string, string> {
  const key = process.env.NEURO_INTERNAL_KEY?.trim();
  return key ? { 'X-Neuro-Key': key } : {};
}

export function sanitizeRequestHeaders(headers: Headers): Record<string, string> {
  const allowed = new Set([
    'authorization',
    'accept',
    'accept-language',
    'content-type',
    'stripe-signature',
    'paypal-transmission-id',
    'paypal-transmission-sig',
    'paypal-transmission-time',
    'paypal-cert-url',
    'paypal-auth-algo',
    CSRF_HEADER,
  ]);
  const out: Record<string, string> = {};
  headers.forEach((value, key) => {
    if (allowed.has(key.toLowerCase())) {
      out[key] = value;
    }
  });
  // Tell the backend who the caller is, from the trusted-proxy resolution and
  // never the raw inbound header, so its trial cap and rate limits stop keying
  // on this host. The backend must list this host in its TRUSTED_PROXIES.
  const ip = resolveClientIp(headers);
  if (ip !== 'unknown') out['X-Forwarded-For'] = ip;
  return out;
}

export function sanitizeResponseHeaders(upstream: Response): Headers {
  const hopByHop = new Set([
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade',
  ]);
  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!hopByHop.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  headers.set('Cache-Control', 'no-store, private');
  return headers;
}

class ValidationError extends Error {}
export { ValidationError };

class PayloadTooLargeError extends Error {}
export { PayloadTooLargeError };

export async function readJsonBody(req: NextRequest, maxBytes = 1024 * 1024): Promise<unknown> {
  const contentType = req.headers.get('content-type') || '';
  if (!contentType.toLowerCase().includes('application/json')) {
    throw new ValidationError('Invalid content type');
  }
  // Refuse an honest oversize body before buffering it; the post-read check
  // below still covers chunked bodies that carry no content-length.
  const declared = Number(req.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > maxBytes) {
    throw new PayloadTooLargeError('Payload too large');
  }
  const text = await req.text();
  if (text.length > maxBytes) {
    throw new PayloadTooLargeError('Payload too large');
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new ValidationError('Invalid JSON');
  }
}

/**
 * The response a proxy route returns when the upstream call threw.
 *
 * Error text from `fetch` carries the upstream host, port and resolver output
 * (`connect ECONNREFUSED 10.0.3.7:8003`), so it is logged here and never sent
 * to the browser. Only a ValidationError message is user-facing: the validators
 * write it for the caller.
 */
export function proxyErrorResponse(err: unknown, label: string, upstreamUrl?: string): NextResponse {
  if (err instanceof ValidationError) {
    return NextResponse.json({ error: err.message }, { status: 400 });
  }
  if (err instanceof PayloadTooLargeError) {
    return NextResponse.json({ error: err.message }, { status: 413 });
  }
  const msg = err instanceof Error ? err.message : 'Proxy error';
  const errName = err instanceof Error ? err.constructor.name : 'Unknown';
  console.error(`${label} proxy error [${errName}] upstream=${upstreamUrl || 'N/A'}:`, msg);

  const lower = msg.toLowerCase();
  const isConnectionError =
    err instanceof TypeError ||
    lower.includes('fetch failed') ||
    lower.includes('network') ||
    lower.includes('econnrefused') ||
    lower.includes('etimedout');
  if (isConnectionError) {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 504 });
  }
  return NextResponse.json({ error: 'Proxy error' }, { status: 502 });
}

// Preset IDs follow the pattern: one or more lowercase alphanumeric / hyphen / underscore tokens.
// Examples: "auto-budget", "multi-perspective-premium", "research-budget", "web-search".
const VALID_PRESET_PATTERN = /^[a-z][a-z0-9_-]{1,64}$/;

export function validateRunRequest(body: unknown): RunRequest {
  if (!body || typeof body !== 'object') {
    throw new ValidationError('Invalid body');
  }
  const b = body as Record<string, unknown>;

  if (typeof b.problem !== 'string') {
    throw new ValidationError('Problem must be a string');
  }
  if (b.problem.length === 0) {
    throw new ValidationError('Problem cannot be empty');
  }
  if (b.problem.length > VALIDATION_LIMITS.problemMaxLength) {
    // Pinned locale: bare toLocaleString() follows the *server's* locale, so a
    // host running de-DE rendered the limit as "10.000 characters" to an English
    // user, who reads that as ten. The copy around it is English either way.
    throw new ValidationError(`Problem exceeds ${VALIDATION_LIMITS.problemMaxLength.toLocaleString('en-US')} characters`);
  }
  if (typeof b.preset !== 'string' || !VALID_PRESET_PATTERN.test(b.preset)) {
    throw new ValidationError('Invalid preset');
  }
  if (typeof b.top_k !== 'number' || !Number.isInteger(b.top_k) || b.top_k < VALIDATION_LIMITS.topKMin || b.top_k > VALIDATION_LIMITS.topKMax) {
    throw new ValidationError('Invalid top_k');
  }
  if (typeof b.sequential !== 'boolean') {
    throw new ValidationError('Invalid sequential');
  }
  if (typeof b.enhance_prompt !== 'boolean') {
    throw new ValidationError('Invalid enhance_prompt');
  }

  const result: RunRequest = {
    problem: b.problem,
    preset: b.preset,
    top_k: b.top_k,
    sequential: b.sequential,
    enhance_prompt: b.enhance_prompt,
  };

  if (typeof b.expert === 'boolean') result.expert = b.expert;
  if (typeof b.web_search === 'boolean') result.web_search = b.web_search;
  if (typeof b.smart_search === 'boolean') result.smart_search = b.smart_search;
  if (typeof b.client_run_id === 'string') result.client_run_id = b.client_run_id;
  if (Array.isArray(b.attachments)) result.attachments = b.attachments as RunRequest['attachments'];
  if (typeof b.jurisdiction === 'string' && b.jurisdiction.length <= 200) result.jurisdiction = b.jurisdiction;
  if (b.facts && typeof b.facts === 'object' && !Array.isArray(b.facts)) {
    const facts = Object.entries(b.facts as Record<string, unknown>)
      .filter((e): e is [string, string] => typeof e[1] === 'string' && e[0].length <= 200 && e[1].length <= 200)
      .slice(0, 3);
    if (facts.length > 0) result.facts = Object.fromEntries(facts);
  }

  return result;
}

export function validateRunFollowupRequest(body: unknown): import('./types').RunFollowupRequest {
  if (!body || typeof body !== 'object') {
    throw new ValidationError('Invalid body');
  }
  const b = body as Record<string, unknown>;

  if (typeof b.question !== 'string') {
    throw new ValidationError('Question must be a string');
  }
  if (b.question.length === 0) {
    throw new ValidationError('Question cannot be empty');
  }
  if (b.question.length > VALIDATION_LIMITS.questionMaxLength) {
    throw new ValidationError(`Question exceeds ${VALIDATION_LIMITS.questionMaxLength.toLocaleString('en-US')} characters`);
  }
  if (typeof b.preset !== 'string' || !VALID_PRESET_PATTERN.test(b.preset)) {
    throw new ValidationError('Invalid preset');
  }
  if (typeof b.top_k !== 'number' || !Number.isInteger(b.top_k) || b.top_k < VALIDATION_LIMITS.topKMin || b.top_k > VALIDATION_LIMITS.topKMax) {
    throw new ValidationError('Invalid top_k');
  }
  if (typeof b.sequential !== 'boolean') {
    throw new ValidationError('Invalid sequential');
  }
  if (typeof b.enhance_prompt !== 'boolean') {
    throw new ValidationError('Invalid enhance_prompt');
  }
  if (typeof b.conversation_id !== 'string' || b.conversation_id.length === 0) {
    throw new ValidationError('Invalid conversation_id');
  }
  if (!Array.isArray(b.history)) {
    throw new ValidationError('Invalid history');
  }
  const history = (b.history as unknown[]).map((turn, i) => {
    if (!turn || typeof turn !== 'object') throw new ValidationError(`Invalid history[${i}]`);
    const t = turn as Record<string, unknown>;
    if (t.role !== 'user' && t.role !== 'assistant') throw new ValidationError(`Invalid history[${i}].role`);
    if (typeof t.content !== 'string') throw new ValidationError(`Invalid history[${i}].content`);
    return { role: t.role as 'user' | 'assistant', content: t.content };
  });
  if (typeof b.previous_synthesis !== 'string') {
    throw new ValidationError('Invalid previous_synthesis');
  }
  const agent_model =
    b.agent_model === null || b.agent_model === undefined ? null
    : typeof b.agent_model === 'string' ? b.agent_model
    : null;

  const result: import('./types').RunFollowupRequest = {
    question: b.question,
    preset: b.preset,
    top_k: b.top_k,
    sequential: b.sequential,
    enhance_prompt: b.enhance_prompt,
    conversation_id: b.conversation_id,
    history,
    previous_synthesis: b.previous_synthesis,
    agent_model,
  };

  if (typeof b.expert === 'boolean') result.expert = b.expert;
  if (typeof b.web_search === 'boolean') result.web_search = b.web_search;
  if (typeof b.smart_search === 'boolean') result.smart_search = b.smart_search;
  if (typeof b.client_run_id === 'string') result.client_run_id = b.client_run_id;
  if (Array.isArray(b.attachments)) result.attachments = b.attachments as import('./types').RunFollowupRequest['attachments'];

  return result;
}

export function validateCalculateRequest(body: unknown): { expression: string } {
  if (!body || typeof body !== 'object') {
    throw new ValidationError('Invalid body');
  }
  const b = body as Record<string, unknown>;
  if (
    typeof b.expression !== 'string' ||
    b.expression.length === 0 ||
    b.expression.length > VALIDATION_LIMITS.expressionMaxLength ||
    !/^[\w\d+\-*/().^\s]+$/u.test(b.expression)
  ) {
    throw new ValidationError('Invalid expression');
  }
  return { expression: b.expression };
}

const SEARCH_SOURCE_TYPES = new Set(['general', 'academic', 'social', 'news', 'code']);

export function validateSearchRequest(body: unknown): { query: string; source_type: string; num_results: number; smart: boolean } {
  if (!body || typeof body !== 'object') {
    throw new ValidationError('Invalid body');
  }
  const b = body as Record<string, unknown>;
  if (typeof b.query !== 'string' || b.query.length === 0 || b.query.length > VALIDATION_LIMITS.queryMaxLength) {
    throw new ValidationError('Invalid query');
  }
  const sourceType = typeof b.source_type === 'string' ? b.source_type : 'general';
  if (!SEARCH_SOURCE_TYPES.has(sourceType)) {
    throw new ValidationError('Invalid source_type');
  }
  const numResults = typeof b.num_results === 'number' ? b.num_results : 10;
  if (!Number.isInteger(numResults) || numResults < VALIDATION_LIMITS.numResultsMin || numResults > VALIDATION_LIMITS.numResultsMax) {
    throw new ValidationError('Invalid num_results');
  }
  const smart = typeof b.smart === 'boolean' ? b.smart : false;
  return { query: b.query, source_type: sourceType, num_results: numResults, smart };
}

// Rate limiting
const RATE_LIMITS: Record<string, { limit: number; windowMs: number }> = {
  run: { limit: 10, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  // A resume restarts pipeline work on the backend, so it costs what a run
  // costs -- same bucket size. Without this entry it would fall through to
  // `default` (30) and sit three times looser than the run it resumes.
  'pipeline-resume': { limit: 10, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  // Agent callers are servers, not browser tabs, and often share an egress
  // IP (NAT, a datacenter range). This is a coarse outer guard only — the
  // authoritative, per-account limit is enforced by the backend's
  // check_rate_limit, which buckets by user id once the bearer key resolves.
  'agent-run': { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  calculate: { limit: 20, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  stop: { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  cache: { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  search: { limit: 20, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'generate-image': { limit: 10, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  estimate: { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  gate: { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'error-report': { limit: 10, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'account-delete': { limit: 3, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  // Each accepted submission sends an email through Resend; a person writes
  // a handful at most.
  contact: { limit: 5, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  // A ticket is single-use and 30s-lived (backend WS_TICKET_TTL_SECONDS) --
  // a legitimate client fetches one per connect/reconnect, so this stays
  // tight without blocking normal reconnect-with-backoff behavior.
  'websocket-ticket': { limit: 20, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'provenance-inspect': { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'provenance-scrub': { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'provenance-rewrite': { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  // Each checkout creates a Stripe/PayPal session upstream, so an unbounded
  // caller burns a third-party quota, not just ours. Tighter than `default`
  // for that reason; a real user clicks upgrade a handful of times at most.
  'billing-checkout': { limit: 10, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  'billing-portal': { limit: 10, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
  default: { limit: 30, windowMs: SECURITY_CONSTANTS.rateLimitWindowMs },
};

type RateLimitBucket = { count: number; resetAt: number };
const rateLimitStore = new Map<string, RateLimitBucket>();
let rateLimitCallCount = 0;

let proxyTopologyWarned = false;

/**
 * OPS-9. With no TRUSTED_PROXIES, the rightmost hop is taken as the client.
 * Behind a CDN plus a load balancer that hop is the CDN's edge, so every user
 * shares one rate-limit bucket. More than one hop in production means a proxy
 * chain that was never declared: say so once, loudly, and flag it in
 * /api/health. Requests are not refused; the backend limiter is the real control.
 */
function warnUndeclaredProxyTopology(hopCount: number): void {
  if (proxyTopologyWarned || process.env.NODE_ENV !== 'production') return;
  proxyTopologyWarned = true;
  console.error(
    `X-Forwarded-For has ${hopCount} hops but TRUSTED_PROXIES is unset: rate limits ` +
      'may key every user to one proxy address. Set TRUSTED_PROXIES (see DEPLOY.md).',
  );
}

/** True once a multi-hop X-Forwarded-For arrived in production with no TRUSTED_PROXIES. */
export function proxyTopologyUndeclared(): boolean {
  return proxyTopologyWarned;
}

/**
 * The rightmost X-Forwarded-For hop that is not a trusted proxy, mirroring
 * the backend's api/client_ip.py. The leftmost entry is whatever the client
 * sent, so trusting it let anyone pick a fresh rate-limit bucket per request.
 * The rightmost hop was appended by the proxy in front of us.
 */
export function getClientIp(req: NextRequest): string {
  return resolveClientIp(req.headers);
}

/**
 * With no TRUSTED_PROXIES nothing in X-Forwarded-For or X-Real-IP is believed:
 * a directly exposed server would let any caller pick a fresh rate-limit
 * bucket per request. The key collapses to 'unknown' (one shared bucket)
 * until the proxy chain is declared. Route handlers expose no peer address.
 */
export function resolveClientIp(headers: Headers): string {
  const trusted = new Set(
    (process.env.TRUSTED_PROXIES || '').split(',').map((s) => s.trim()).filter(Boolean),
  );
  const forwarded = headers.get('x-forwarded-for');
  if (trusted.size === 0) {
    if (forwarded) {
      const hops = forwarded.split(',').filter((s) => s.trim()).length;
      if (hops > 1) warnUndeclaredProxyTopology(hops);
    }
    return 'unknown';
  }
  if (forwarded) {
    const hops = forwarded.split(',').map((s) => s.trim()).filter(Boolean);
    for (let i = hops.length - 1; i >= 0; i--) {
      if (!trusted.has(hops[i])) return hops[i];
    }
  }
  // X-Real-IP is only as trustworthy as the proxy that sets it (UI-11).
  return headers.get('x-real-ip') || 'unknown';
}

function _evictExpiredRateLimitBuckets(now: number): void {
  for (const [key, bucket] of rateLimitStore) {
    if (now > bucket.resetAt) {
      rateLimitStore.delete(key);
    }
  }
}

function _pruneRateLimitStore(): void {
  if (rateLimitStore.size <= SECURITY_CONSTANTS.rateLimitMaxEntries) return;
  // Evict oldest buckets by resetAt (FIFO-style)
  const entries = Array.from(rateLimitStore.entries());
  entries.sort((a, b) => a[1].resetAt - b[1].resetAt);
  const toRemove = entries.slice(0, SECURITY_CONSTANTS.rateLimitEvictionBatch);
  for (const [key] of toRemove) {
    rateLimitStore.delete(key);
  }
}

export function rateLimit(
  req: NextRequest,
  action: keyof typeof RATE_LIMITS
): { allowed: boolean; retryAfter: number } {
  const ip = getClientIp(req);
  const key = `${ip}:${action}`;
  const cfg = RATE_LIMITS[action] || RATE_LIMITS.default;
  const now = Date.now();

  // Periodic eviction to prevent unbounded growth
  rateLimitCallCount += 1;
  if (rateLimitCallCount % SECURITY_CONSTANTS.rateLimitCleanupModulo === 0) {
    _evictExpiredRateLimitBuckets(now);
    _pruneRateLimitStore();
  }

  const bucket = rateLimitStore.get(key);
  if (!bucket || now > bucket.resetAt) {
    rateLimitStore.set(key, { count: 1, resetAt: now + cfg.windowMs });
    return { allowed: true, retryAfter: 0 };
  }

  if (bucket.count >= cfg.limit) {
    return { allowed: false, retryAfter: Math.ceil((bucket.resetAt - now) / 1000) };
  }

  bucket.count += 1;
  rateLimitStore.set(key, bucket);
  return { allowed: true, retryAfter: 0 };
}
