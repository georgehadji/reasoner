// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

/**
 * PR 9 of docs/plans/audit-remediation-2-2026-10-20.md: the run lifecycle.
 *
 * - UI-1: a resumed run had no AbortController, so Stop flipped `running`
 *   while the billed stream carried on.
 * - UI-2: Enter twice during the gate check started two runs; the guard read
 *   `running`, which the gate check had not set yet.
 * - UI-4: Stop posted a bare /api/stop, the admin "stop every user's run".
 */

const mocked = vi.hoisted(() => ({ fetchWithCsrf: vi.fn() }));
vi.mock('@/lib/security-client', () => ({ fetchWithCsrf: mocked.fetchWithCsrf }));

import { useRunController } from './useRunController';
import { resumePipelineStream } from '@/lib/api-client';

beforeEach(() => {
  mocked.fetchWithCsrf.mockReset();
  mocked.fetchWithCsrf.mockResolvedValue(new Response('{}'));
});

describe('useRunController', () => {
  it('refuses a second run while one is active, then allows one after finish', () => {
    const { result } = renderHook(() => useRunController(vi.fn()));
    const first = result.current.begin();
    expect(first).not.toBeNull();
    expect(result.current.begin()).toBeNull();
    result.current.finish(first!);
    expect(result.current.begin()).not.toBeNull();
  });

  it('stop aborts the run signal and stops it on the server by run_id', () => {
    const wsStop = vi.fn();
    const { result } = renderHook(() => useRunController(wsStop));
    const ticket = result.current.begin()!;
    ticket.clientRunId = 'run-a b';

    result.current.stop();

    expect(ticket.abort.signal.aborted).toBe(true);
    expect(wsStop).toHaveBeenCalledWith('run-a b');
    expect(mocked.fetchWithCsrf).toHaveBeenCalledTimes(1);
    expect(mocked.fetchWithCsrf.mock.calls[0][0]).toBe('/api/stop?run_id=run-a%20b');
    expect(result.current.isActive()).toBe(false);
  });

  it('never posts a bare /api/stop', () => {
    const { result } = renderHook(() => useRunController(vi.fn()));
    result.current.stop(); // nothing running
    const ticket = result.current.begin()!; // gating: no run id yet
    result.current.stop();
    expect(ticket.abort.signal.aborted).toBe(true);
    expect(mocked.fetchWithCsrf).not.toHaveBeenCalled();
  });

  it('a stopped run finishing late does not end the next run', () => {
    const { result } = renderHook(() => useRunController(vi.fn()));
    const old = result.current.begin()!;
    result.current.stop();
    const next = result.current.begin()!;
    result.current.finish(old);
    expect(result.current.isActive()).toBe(true);
    result.current.finish(next);
    expect(result.current.isActive()).toBe(false);
  });

  it('unmount stops the active run', () => {
    const { result, unmount } = renderHook(() => useRunController(vi.fn()));
    const ticket = result.current.begin()!;
    unmount();
    expect(ticket.abort.signal.aborted).toBe(true);
  });
});

describe('resumePipelineStream', () => {
  it('passes the run signal to the fetch, so Stop can end a resume', async () => {
    mocked.fetchWithCsrf.mockResolvedValue(new Response('data: {}\n\n'));
    const abort = new AbortController();
    await resumePipelineStream('p1', abort.signal);
    expect(mocked.fetchWithCsrf.mock.calls[0][1].signal).toBe(abort.signal);
  });
});
