import { describe, expect, it, vi } from 'vitest';
import { readSSEStream } from './sse-reader';

function streamOf(text: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
}

describe('readSSEStream', () => {
  it('skips a malformed line and still delivers the next event', async () => {
    const onEvent = vi.fn();
    await readSSEStream(streamOf('data: {not json\ndata: {"type":"done"}\n'), onEvent);
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith({ type: 'done' });
  });

  it('lets an error thrown by the handler reject the read', async () => {
    const onEvent = vi.fn(() => { throw new Error('handler failed'); });
    await expect(readSSEStream(streamOf('data: {"type":"done"}\n'), onEvent)).rejects.toThrow('handler failed');
  });

  it('lets a handler error on the final unterminated line reject the read', async () => {
    const onEvent = vi.fn(() => { throw new Error('handler failed'); });
    await expect(readSSEStream(streamOf('data: {"type":"done"}'), onEvent)).rejects.toThrow('handler failed');
  });
});
