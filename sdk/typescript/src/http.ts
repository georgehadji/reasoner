/**
 * HTTP transport: authentication, retries, and abort plumbing.
 *
 * Uses the global `fetch`, so the SDK runs unmodified on Node 20+, Bun, Deno,
 * browsers, and edge runtimes with no dependencies to keep current.
 */

import {
  AbortError,
  ConnectionError,
  errorFromResponse,
  parseRetryAfter,
  type ReasonerError,
} from './errors.js';

/** Statuses worth retrying: rate limiting and transient dependency failures. */
const RETRYABLE = new Set([429, 502, 503, 504]);

const DEFAULT_BASE_URL = 'https://reasoner.app';
const DEFAULT_MAX_RETRIES = 2;
const DEFAULT_TIMEOUT_MS = 600_000;
const BACKOFF_BASE_MS = 500;
const BACKOFF_CAP_MS = 20_000;

/** Configuration for {@link ReasonerClient}. */
export interface ClientOptions {
  /**
   * A Reasoner API key (`rsn_live_…`).
   *
   * Read it from the environment; never commit one. Defaults to
   * `process.env.REASONER_API_KEY` where a process environment exists.
   */
  apiKey?: string;
  /** API root. Point this at `http://127.0.0.1:8003` for a local backend. */
  baseUrl?: string;
  /**
   * Retry attempts for rate-limited and transient failures. Default 2.
   *
   * Only requests that have not yet produced bytes are retried — a stream
   * cannot be resumed mid-flight, so a mid-stream failure surfaces to the
   * caller instead.
   */
  maxRetries?: number;
  /** Per-request timeout in ms. Default 600000 — full runs are slow by design. */
  timeoutMs?: number;
  /** Extra headers applied to every request. */
  headers?: Record<string, string>;
  /** Replacement `fetch`, for tests or custom transports. */
  fetch?: typeof globalThis.fetch;
}

/** Per-call overrides. */
export interface RequestOptions {
  /** Abort the request, or stop consuming a stream. */
  signal?: AbortSignal;
  /** Override {@link ClientOptions.timeoutMs} for this call. */
  timeoutMs?: number;
}

interface SendOptions extends RequestOptions {
  method: string;
  path: string;
  body?: unknown;
  /** Reported on a 409 so the caller can see which key collided. */
  clientRunId?: string;
  /** Streaming responses skip body buffering and JSON parsing. */
  stream?: boolean;
}

function readEnvApiKey(): string | undefined {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
    ?.env;
  return env?.REASONER_API_KEY;
}

/**
 * Merge abort signals into one.
 *
 * Hand-rolled rather than `AbortSignal.any` so the SDK does not require a
 * runtime newer than its `fetch` baseline.
 */
function linkSignals(signals: (AbortSignal | undefined)[]): {
  signal: AbortSignal;
  dispose: () => void;
} {
  const controller = new AbortController();
  const live = signals.filter((s): s is AbortSignal => Boolean(s));

  const abort = (reason: unknown) => controller.abort(reason);
  const already = live.find((s) => s.aborted);
  if (already) {
    abort(already.reason);
    return { signal: controller.signal, dispose: () => {} };
  }

  const listeners = live.map((source) => {
    const onAbort = () => abort(source.reason);
    source.addEventListener('abort', onAbort, { once: true });
    return () => source.removeEventListener('abort', onAbort);
  });

  return {
    signal: controller.signal,
    dispose: () => listeners.forEach((remove) => remove()),
  };
}

/** Exponential backoff with full jitter, honouring `Retry-After` when present. */
function backoffMs(attempt: number, retryAfterMs: number | undefined): number {
  if (retryAfterMs !== undefined) return Math.min(retryAfterMs, BACKOFF_CAP_MS);
  const ceiling = Math.min(BACKOFF_BASE_MS * 2 ** attempt, BACKOFF_CAP_MS);
  return Math.random() * ceiling;
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new AbortError());
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new AbortError());
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

function isAbort(error: unknown): boolean {
  return (
    error instanceof AbortError ||
    (error instanceof Error && (error.name === 'AbortError' || error.name === 'TimeoutError'))
  );
}

/** Authenticated HTTP transport with retry and abort handling. */
export class HttpTransport {
  private readonly apiKey: string | undefined;
  private readonly baseUrl: string;
  private readonly maxRetries: number;
  private readonly timeoutMs: number;
  private readonly extraHeaders: Record<string, string>;
  private readonly fetchImpl: typeof globalThis.fetch;

  constructor(options: ClientOptions = {}) {
    this.apiKey = options.apiKey ?? readEnvApiKey();
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.extraHeaders = options.headers ?? {};

    const impl = options.fetch ?? globalThis.fetch;
    if (typeof impl !== 'function') {
      throw new TypeError(
        'No global fetch available. Use Node 20+, or pass a fetch implementation via the `fetch` option.',
      );
    }
    // Unbound `fetch` throws "Illegal invocation" in browsers.
    this.fetchImpl = impl.bind(globalThis);
  }

  private buildHeaders(hasBody: boolean, streaming: boolean): Headers {
    const headers = new Headers(this.extraHeaders);
    if (hasBody) headers.set('Content-Type', 'application/json');
    headers.set('Accept', streaming ? 'text/event-stream' : 'application/json');
    if (this.apiKey) headers.set('Authorization', `Bearer ${this.apiKey}`);
    return headers;
  }

  /**
   * Issue a request, retrying transient failures.
   *
   * Retries reuse the same `client_run_id`, which is what makes them safe on a
   * non-idempotent POST: the server rejects a genuine duplicate with 409 rather
   * than running the pipeline twice. Retryable statuses are all raised by
   * dependencies that run *before* the run is registered, so a retry cannot
   * collide with its own first attempt.
   */
  async send(options: SendOptions): Promise<Response> {
    const url = `${this.baseUrl}${options.path}`;
    const headers = this.buildHeaders(options.body !== undefined, options.stream === true);
    const body = options.body === undefined ? undefined : JSON.stringify(options.body);
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;

    let lastError: ReasonerError | undefined;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const timeout = AbortSignal.timeout(timeoutMs);
      const { signal, dispose } = linkSignals([options.signal, timeout]);

      let response: Response;
      try {
        response = await this.fetchImpl(url, {
          method: options.method,
          headers,
          body,
          signal,
        });
      } catch (error) {
        dispose();
        if (options.signal?.aborted) throw new AbortError();
        if (isAbort(error)) {
          throw new ConnectionError(`Request to ${options.path} timed out`, error);
        }
        lastError = new ConnectionError(
          `Request to ${options.path} failed: ${error instanceof Error ? error.message : String(error)}`,
          error,
        );
        if (attempt === this.maxRetries) throw lastError;
        await sleep(backoffMs(attempt, undefined), options.signal);
        continue;
      }

      if (response.ok) {
        // Streaming responses own the signal until the caller stops reading.
        if (!options.stream) dispose();
        return response;
      }

      const text = await response.text().catch(() => '');
      dispose();

      const error = errorFromResponse(
        response.status,
        text,
        response.headers,
        options.clientRunId,
      );

      if (!RETRYABLE.has(response.status) || attempt === this.maxRetries) throw error;

      lastError = error;
      await sleep(
        backoffMs(attempt, parseRetryAfter(response.headers.get('Retry-After'))),
        options.signal,
      );
    }

    // Unreachable: the loop either returns or throws on its final attempt.
    throw lastError ?? new ConnectionError(`Request to ${options.path} failed`);
  }

  /** Send a request and parse the response as JSON. */
  async json<T>(options: SendOptions): Promise<T> {
    const response = await this.send(options);
    return (await response.json()) as T;
  }
}
