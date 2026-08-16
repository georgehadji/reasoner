/**
 * Error types for the Reasoner API.
 *
 * Every non-2xx response becomes a subclass of {@link ReasonerError}, chosen by
 * status code, so callers can branch on the failure kind without inspecting
 * numbers. The status codes mirror the published error table: 400 malformed,
 * 401 bad credentials, 402 out of credits, 403 scope failure, 409 duplicate
 * run, 429 rate limited, 5xx dependency trouble.
 */

/** Base class for every error raised by this SDK. */
export class ReasonerError extends Error {
  /** HTTP status that produced this error, or 0 for transport failures. */
  readonly status: number;
  /** Raw response body, truncated to keep stack traces readable. */
  readonly body: string;
  /** Parsed response body when it was valid JSON. */
  readonly data: unknown;

  constructor(message: string, status: number, body = '', data: unknown = undefined) {
    super(message);
    this.name = new.target.name;
    this.status = status;
    this.body = body;
    this.data = data;
  }
}

/** 400 — the request payload was rejected by validation. */
export class BadRequestError extends ReasonerError {}

/** 401 — missing, invalid, or revoked credentials. */
export class AuthenticationError extends ReasonerError {}

/**
 * 402 — the account's credit balance is exhausted.
 *
 * Runs are post-paid from actual model spend, so this gates *new* runs; a run
 * already in flight is never interrupted by it.
 */
export class InsufficientCreditsError extends ReasonerError {}

/** 403 — the key authenticated but lacks the scope the call needs. */
export class PermissionError extends ReasonerError {}

/**
 * 409 — a run with this `client_run_id` is already in progress.
 *
 * The original run is still executing and will still be charged exactly once.
 * Read its result rather than resubmitting under a fresh id.
 */
export class DuplicateRunError extends ReasonerError {
  /** The `client_run_id` that collided. */
  readonly clientRunId: string | undefined;

  constructor(
    message: string,
    status: number,
    body: string,
    data: unknown,
    clientRunId: string | undefined,
  ) {
    super(message, status, body, data);
    this.clientRunId = clientRunId;
  }
}

/** 429 — rate limited. Wait {@link RateLimitError.retryAfterMs} before retrying. */
export class RateLimitError extends ReasonerError {
  /** Milliseconds to wait, taken from `Retry-After` when the server sent one. */
  readonly retryAfterMs: number | undefined;

  constructor(
    message: string,
    status: number,
    body: string,
    data: unknown,
    retryAfterMs: number | undefined,
  ) {
    super(message, status, body, data);
    this.retryAfterMs = retryAfterMs;
  }
}

/** 5xx — the server or one of its dependencies failed. Safe to retry with backoff. */
export class ServerError extends ReasonerError {}

/** The request never produced a response: network failure, DNS, TLS, or timeout. */
export class ConnectionError extends ReasonerError {
  constructor(message: string, cause?: unknown) {
    super(message, 0);
    this.cause = cause;
  }
}

/** The caller aborted the request or stopped consuming the stream. */
export class AbortError extends ReasonerError {
  constructor(message = 'Request aborted') {
    super(message, 0);
  }
}

const BODY_LIMIT = 2000;

/**
 * Render a FastAPI error body as a single readable line.
 *
 * FastAPI reports validation failures as `detail: [{loc, msg}, ...]`, which is
 * unreadable when stringified whole. Field paths are flattened to `field: msg`
 * and the `body` prefix every entry carries is dropped.
 */
export function formatApiError(status: number, data: unknown): string {
  if (data && typeof data === 'object') {
    const payload = data as Record<string, unknown>;
    const detail = payload.detail;

    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          const err = item as Record<string, unknown>;
          const loc = Array.isArray(err.loc)
            ? err.loc.filter((part) => part !== 'body').join('.')
            : '';
          const msg = typeof err.msg === 'string' ? err.msg : 'Invalid request';
          return loc ? `${loc}: ${msg}` : msg;
        })
        .filter((m): m is string => Boolean(m));
      if (messages.length > 0) return `HTTP ${status}: ${messages.join('; ')}`;
    }

    // Rate-limit responses nest their explanation one level down.
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const nested = detail as Record<string, unknown>;
      if (typeof nested.error === 'string') return `HTTP ${status}: ${nested.error}`;
    }

    if (typeof detail === 'string') return `HTTP ${status}: ${detail}`;
    if (typeof payload.error === 'string') return `HTTP ${status}: ${payload.error}`;
  }

  return `HTTP ${status}`;
}

/**
 * Parse `Retry-After`, which may be either a delay in seconds or an HTTP date.
 *
 * @returns milliseconds to wait, or undefined when the header is absent or unparseable.
 */
export function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined;

  const seconds = Number(header);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;

  const date = Date.parse(header);
  if (!Number.isNaN(date)) return Math.max(0, date - Date.now());

  return undefined;
}

/** Build the right {@link ReasonerError} subclass for a failed response. */
export function errorFromResponse(
  status: number,
  body: string,
  headers: Headers,
  clientRunId?: string,
): ReasonerError {
  let data: unknown;
  try {
    data = JSON.parse(body);
  } catch {
    data = undefined;
  }

  const message = formatApiError(status, data) || `HTTP ${status}`;
  const truncated = body.slice(0, BODY_LIMIT);

  switch (status) {
    case 400:
    case 422:
      return new BadRequestError(message, status, truncated, data);
    case 401:
      return new AuthenticationError(message, status, truncated, data);
    case 402:
      return new InsufficientCreditsError(message, status, truncated, data);
    case 403:
      return new PermissionError(message, status, truncated, data);
    case 409:
      return new DuplicateRunError(message, status, truncated, data, clientRunId);
    case 429:
      return new RateLimitError(
        message,
        status,
        truncated,
        data,
        parseRetryAfter(headers.get('Retry-After')),
      );
    default:
      if (status >= 500) return new ServerError(message, status, truncated, data);
      return new ReasonerError(message, status, truncated, data);
  }
}
