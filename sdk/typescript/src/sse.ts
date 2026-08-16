/**
 * Server-Sent Events parsing.
 *
 * Implements the framing rules from the SSE spec rather than scanning for
 * `data: ` line by line: events end at a blank line, `data:` fields accumulate
 * across lines within one event, the space after the colon is optional, and
 * `:`-prefixed comment lines are keepalives to be dropped. The Reasoner API
 * currently emits one single-line JSON `data:` field per frame, but a proxy
 * that re-chunks the stream or a future multi-line payload would silently
 * corrupt a naive parser.
 */

/** Event boundary: a blank line, in any of the three line-ending conventions. */
const FRAME_END = /\r\n\r\n|\n\n|\r\r/;
const LINE_BREAK = /\r\n|\n|\r/;

/**
 * Split a byte stream into raw SSE frames.
 *
 * Yields the text of each frame with its terminating blank line removed. A
 * trailing unterminated frame is yielded at end of stream, since the server
 * closing the connection is itself a boundary.
 */
export async function* readFrames(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<string, void, undefined> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      if (signal?.aborted) return;

      const { done, value } = await reader.read();
      if (done) break;

      // `stream: true` holds back bytes that split a multi-byte character.
      buffer += decoder.decode(value, { stream: true });

      for (;;) {
        const match = FRAME_END.exec(buffer);
        if (!match) break;
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        if (frame) yield frame;
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) yield buffer;
  } finally {
    reader.releaseLock();
  }
}

/**
 * Extract the joined `data` payload from one raw frame.
 *
 * @returns the payload, or null for frames carrying no data (comments,
 *          heartbeats, or metadata-only fields such as `event:` and `id:`).
 */
export function frameToData(frame: string): string | null {
  const parts: string[] = [];

  for (const line of frame.split(LINE_BREAK)) {
    // Blank lines cannot appear mid-frame; `:` prefixes a comment.
    if (!line || line.startsWith(':')) continue;

    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    if (field !== 'data') continue;

    let value = colon === -1 ? '' : line.slice(colon + 1);
    // Exactly one leading space is part of the framing, not the payload.
    if (value.startsWith(' ')) value = value.slice(1);
    parts.push(value);
  }

  return parts.length > 0 ? parts.join('\n') : null;
}

/**
 * Parse an SSE byte stream into JSON objects.
 *
 * Malformed frames are skipped rather than thrown: a parsing failure must never
 * tear down a stream the caller is still reading, and the API is explicit that
 * unrecognised frames should be ignored.
 */
export async function* parseSSE<T>(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<T, void, undefined> {
  for await (const frame of readFrames(stream, signal)) {
    const data = frameToData(frame);
    if (data === null) continue;

    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      continue;
    }

    if (parsed !== null && typeof parsed === 'object') {
      yield parsed as T;
    }
  }
}
