// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAsyncAction } from './useAsyncAction';

const deferred = () => {
  let resolve!: () => void;
  let reject!: (e: unknown) => void;
  const p = new Promise<void>((res, rej) => ((resolve = res), (reject = rej)));
  return { p, resolve, reject };
};

describe('useAsyncAction', () => {
  it('ignores a second run (any key) while one is pending', async () => {
    const { result } = renderHook(() => useAsyncAction());
    const d = deferred();
    let calls = 0;
    await act(async () => {
      void result.current.run('a', () => ((calls++, d.p)));
      void result.current.run('b', () => ((calls++, d.p))); // same tick: no re-render between
    });
    expect(calls).toBe(1);
    expect(result.current.status).toBe('pending');
    expect(result.current.key).toBe('a');
    await act(async () => d.resolve());
    expect(result.current.status).toBe('ok');
  });

  it('pageshow with persisted resets a pending action; a late settle cannot overwrite it', async () => {
    const { result } = renderHook(() => useAsyncAction());
    const d = deferred();
    await act(async () => void result.current.run('a', () => d.p));
    expect(result.current.pending).toBe(true);
    act(() => {
      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    });
    expect(result.current.status).toBe('idle');
    await act(async () => d.reject(new Error('late')));
    expect(result.current.status).toBe('idle');
    // and a fresh run is allowed again
    await act(async () => void result.current.run('a', async () => {}));
    expect(result.current.status).toBe('ok');
  });

  it('a non-persisted pageshow does not touch a pending action', async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => void result.current.run('a', () => new Promise(() => {})));
    act(() => {
      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: false }));
    });
    expect(result.current.pending).toBe(true);
  });

  it('pageshow with persisted also clears ok (success that navigated away)', async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => void result.current.run('a', async () => {}));
    expect(result.current.status).toBe('ok');
    act(() => {
      window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    });
    expect(result.current.status).toBe('idle');
  });

  it('error then retry works and clears the error', async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => void result.current.run('a', async () => { throw new Error('boom'); }));
    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('boom');
    await act(async () => void result.current.run('a', async () => {}));
    expect(result.current.status).toBe('ok');
    expect(result.current.error).toBe('');
  });
});
