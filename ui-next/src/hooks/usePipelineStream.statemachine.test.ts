// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

/** SM-U3: docs/plans/implicit-state-machines-2026-11-11.md 1.3 */
const mocked = vi.hoisted(() => ({ fetchWithCsrf: vi.fn() }));
vi.mock('@/lib/security-client', () => ({ fetchWithCsrf: mocked.fetchWithCsrf }));

import { usePipelineStream } from './usePipelineStream';

function sse(lines: string[]) {
  const enc = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(c) {
        for (const l of lines) c.enqueue(enc.encode(`data: ${l}\n\n`));
        c.close();
      },
    }),
    { status: 200 },
  );
}

beforeEach(() => mocked.fetchWithCsrf.mockReset());

describe('SM-U3 usePipelineStream terminal state', () => {
  it('SM-U3: a stream that closes without done/error must surface an error', async () => {
    mocked.fetchWithCsrf.mockResolvedValue(sse([JSON.stringify({ type: 'phase_start', phase: 1 })]));
    const { result } = renderHook(() => usePipelineStream());
    // bug: resolves as success having seen only a non-terminal event
    await expect(
      result.current.startRun({} as never, () => {}, new AbortController().signal),
    ).rejects.toThrow();
  });

  it('SM-U3: the run-signal abort listener is removed once the stream ends', async () => {
    mocked.fetchWithCsrf.mockResolvedValue(sse([JSON.stringify({ type: 'done' })]));
    const ac = new AbortController();
    const remove = vi.spyOn(ac.signal, 'removeEventListener');
    const { result } = renderHook(() => usePipelineStream());
    await result.current.startRun({} as never, () => {}, ac.signal);
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function)); // bug: never called
  });
});
