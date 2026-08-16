import { describe, expect, test } from 'vitest';
import { frameToData, parseSSE, readFrames } from '../src/sse.js';

/** Build a ReadableStream that emits the given strings as separate chunks. */
function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

/** Build a stream from raw bytes, for split multi-byte character tests. */
function byteStreamOf(...chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

async function collect<T>(iterable: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const item of iterable) out.push(item);
  return out;
}

describe('frameToData', () => {
  test('extracts a data payload', () => {
    expect(frameToData('data: {"type":"done"}')).toBe('{"type":"done"}');
  });

  test('treats the space after the colon as optional', () => {
    expect(frameToData('data:{"type":"done"}')).toBe('{"type":"done"}');
  });

  test('strips only one leading space, preserving payload indentation', () => {
    expect(frameToData('data:  padded')).toBe(' padded');
  });

  test('joins multi-line data fields with newlines', () => {
    expect(frameToData('data: {"a":1,\ndata: "b":2}')).toBe('{"a":1,\n"b":2}');
  });

  test('ignores comment lines used as keepalives', () => {
    expect(frameToData(': heartbeat')).toBeNull();
  });

  test('ignores non-data fields', () => {
    expect(frameToData('event: message\nid: 7')).toBeNull();
  });

  test('keeps the data field when other fields accompany it', () => {
    expect(frameToData('event: message\ndata: payload\nid: 7')).toBe('payload');
  });
});

describe('readFrames', () => {
  test('splits on blank lines', async () => {
    const frames = await collect(readFrames(streamOf('data: a\n\ndata: b\n\n')));
    expect(frames).toEqual(['data: a', 'data: b']);
  });

  test('reassembles a frame split across chunk boundaries', async () => {
    const frames = await collect(readFrames(streamOf('data: {"ty', 'pe":"done"}\n\n')));
    expect(frames).toEqual(['data: {"type":"done"}']);
  });

  test('handles CRLF framing', async () => {
    const frames = await collect(readFrames(streamOf('data: a\r\n\r\ndata: b\r\n\r\n')));
    expect(frames).toEqual(['data: a', 'data: b']);
  });

  test('does not split when CR and LF land in different chunks', async () => {
    // A naive normalise-on-append turns this into a false frame boundary.
    const frames = await collect(readFrames(streamOf('data: one\r', '\ndata: two\r\n\r\n')));
    expect(frames).toEqual(['data: one\r\ndata: two']);
  });

  test('yields a trailing frame that the server never terminated', async () => {
    const frames = await collect(readFrames(streamOf('data: a\n\ndata: b')));
    expect(frames).toEqual(['data: a', 'data: b']);
  });

  test('reassembles a multi-byte character split across chunks', async () => {
    const bytes = new TextEncoder().encode('data: "π≈3"\n\n');
    const frames = await collect(
      readFrames(byteStreamOf(bytes.slice(0, 8), bytes.slice(8))),
    );
    expect(frames).toEqual(['data: "π≈3"']);
  });

  test('stops early when the signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const frames = await collect(readFrames(streamOf('data: a\n\n'), controller.signal));
    expect(frames).toEqual([]);
  });
});

describe('parseSSE', () => {
  test('parses JSON events in order', async () => {
    const events = await collect(
      parseSSE<{ type: string }>(
        streamOf('data: {"type":"start"}\n\ndata: {"type":"done"}\n\n'),
      ),
    );
    expect(events.map((e) => e.type)).toEqual(['start', 'done']);
  });

  test('skips malformed frames without ending the stream', async () => {
    const events = await collect(
      parseSSE<{ type: string }>(
        streamOf('data: {"type":"start"}\n\ndata: {not json\n\ndata: {"type":"done"}\n\n'),
      ),
    );
    expect(events.map((e) => e.type)).toEqual(['start', 'done']);
  });

  test('skips keepalive comments', async () => {
    const events = await collect(
      parseSSE<{ type: string }>(streamOf(': ping\n\ndata: {"type":"done"}\n\n')),
    );
    expect(events.map((e) => e.type)).toEqual(['done']);
  });

  test('skips JSON primitives that are not objects', async () => {
    const events = await collect(
      parseSSE<{ type: string }>(streamOf('data: 42\n\ndata: {"type":"done"}\n\n')),
    );
    expect(events.map((e) => e.type)).toEqual(['done']);
  });

  test('surfaces event types the SDK does not model', async () => {
    const events = await collect(
      parseSSE<{ type: string }>(streamOf('data: {"type":"future_event","x":1}\n\n')),
    );
    expect(events).toEqual([{ type: 'future_event', x: 1 }]);
  });
});
