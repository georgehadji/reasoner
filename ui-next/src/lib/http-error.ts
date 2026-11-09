/**
 * One readable line for an HTTP error from the backend.
 *
 * The backend sends `{error, status_code, detail?}`; `error` is the message and
 * `detail` carries what the route wrote for the client (`retry_after`,
 * `upgrade_url`). A 429 used to reach the chat as that whole payload.
 */

export function formatRetryAfter(seconds: number): string {
  const unit = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;
  if (seconds < 60) return unit(Math.max(1, Math.round(seconds)), 'second');
  if (seconds < 3600) return unit(Math.round(seconds / 60), 'minute');
  return unit(Math.round(seconds / 3600), 'hour');
}

export function describeHttpError(status: number, body: string, retryAfterHeader?: string | null): string {
  let data: { error?: unknown; detail?: unknown } | null = null;
  try {
    data = JSON.parse(body);
  } catch {
    data = null;
  }
  const detail = data && typeof data.detail === 'object' && data.detail !== null
    ? (data.detail as Record<string, unknown>)
    : {};
  const serverMessage = typeof data?.error === 'string' ? data.error : '';

  if (status === 429) {
    const title = typeof detail.error === 'string' ? detail.error : serverMessage || 'Rate limit reached';
    const retry = Number(detail.retry_after ?? retryAfterHeader);
    const when = Number.isFinite(retry) && retry > 0 ? ` Try again in ${formatRetryAfter(retry)}.` : '';
    return `${title.replace(/\.$/, '')}.${when}`;
  }
  return serverMessage || `Request failed (HTTP ${status}).`;
}
