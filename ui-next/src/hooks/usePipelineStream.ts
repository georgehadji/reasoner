'use client';

import { useRef, useCallback, useEffect } from 'react';
import { fetchWithCsrf } from '@/lib/security-client';
import { readSSEStream } from '@/lib/sse-reader';
import { PhaseEvent, RunRequest, RunFollowupRequest } from '@/lib/types';
import { API } from '@/lib/config';

export class PipelineError extends Error {
  status: number;
  body: string;
  constructor(status: number, body: string, message: string) {
    super(message);
    this.status = status;
    this.body = body;
    this.name = 'PipelineError';
  }
}

/**
 * Aborts are user-initiated (Stop button, unmount, a new run superseding the
 * old one). The browser surfaces them as a DOMException named 'AbortError'
 * ("signal is aborted without reason"), which must never reach the UI as a
 * pipeline error.
 */
function isAbortError(err: unknown): boolean {
  return typeof err === 'object' && err !== null && (err as { name?: string }).name === 'AbortError';
}

function getDevErrorMessage(status: number, text: string): string {
  if (status === 504) {
    return 'Backend unreachable. Run: uvicorn asgi:app --reload';
  }
  return `HTTP ${status}: ${text.slice(0, 200)}`;
}

export function usePipelineStream() {
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => { abortControllerRef.current?.abort(); }, []);

  const streamEvents = useCallback(
    async (url: string, body: object, onEvent: (ev: PhaseEvent) => void, signal: AbortSignal) => {
      // Abort any in-flight stream before starting a new one. Hold the
      // controller locally: a superseding run replaces the ref outright.
      // `signal` is the run's own (useRunController); Stop aborts through it.
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;
      if (signal.aborted) controller.abort();
      signal.addEventListener('abort', () => controller.abort(), { once: true });

      try {
        const resp = await fetchWithCsrf(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!resp.ok) {
          const text = await resp.text().catch(() => '');
          const isDev = process.env.NODE_ENV !== 'production';
          const message = isDev
            ? getDevErrorMessage(resp.status, text)
            : `HTTP ${resp.status}: ${text.slice(0, 200)}`;
          // eslint-disable-next-line no-console
          console.error('Pipeline HTTP error:', resp.status, text);
          throw new PipelineError(resp.status, text, message);
        }
        if (!resp.body) throw new Error('No response body');

        await readSSEStream(resp.body, onEvent, controller.signal);
      } catch (err) {
        if (controller.signal.aborted || isAbortError(err)) return;
        throw err;
      } finally {
        if (abortControllerRef.current === controller) abortControllerRef.current = null;
      }
    },
    []
  );

  const startRun = useCallback(
    async (req: RunRequest, onEvent: (ev: PhaseEvent) => void, signal: AbortSignal) => {
      await streamEvents(API.RUN, req, onEvent, signal);
    },
    [streamEvents]
  );

  const startFollowup = useCallback(
    async (req: RunFollowupRequest, onEvent: (ev: PhaseEvent) => void, signal: AbortSignal) => {
      await streamEvents(API.RUN_FOLLOWUP, req, onEvent, signal);
    },
    [streamEvents]
  );

  // Stopping is useRunController's job: it aborts the run's signal and stops
  // the run on the server by run_id. The stop that lived here posted a bare
  // /api/stop, which is the admin "stop everyone" call (UI-4).
  return { startRun, startFollowup };
}
