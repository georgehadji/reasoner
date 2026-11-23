'use client';

import { PhaseEvent } from '@/lib/types';

/** Only a malformed line is ignored; an error thrown by `onEvent` propagates to the reader. */
function dispatch(line: string, onEvent: (ev: PhaseEvent) => void): void {
  if (!line.startsWith('data: ')) return;
  let ev: PhaseEvent;
  try {
    ev = JSON.parse(line.slice(6));
  } catch {
    return; // ignore malformed sse lines
  }
  onEvent(ev);
}

/**
 * Read a Server-Sent Events stream from a ReadableStream.
 *
 * @param stream - The ReadableStream to read from (e.g., response.body)
 * @param onEvent - Callback for each parsed PhaseEvent
 * @param signal - Optional AbortSignal for cancellation
 */
export async function readSSEStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (ev: PhaseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        dispatch(line, onEvent);
      }
    }
    // Flush any bytes the decoder held for multi-byte sequences
    buffer += decoder.decode();
    for (const line of buffer.split('\n')) dispatch(line, onEvent);
  } finally {
    reader.releaseLock();
  }
}
