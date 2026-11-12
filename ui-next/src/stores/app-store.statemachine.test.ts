import { beforeEach, describe, expect, it, vi } from 'vitest';

/** SM-U5: docs/plans/implicit-state-machines-2026-11-11.md 1.3 */
const mocked = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ apiFetch: mocked.apiFetch }));

import { useAppStore } from './app-store';

const sub = { tier: 'pro', status: 'active' } as never;

beforeEach(() => {
  mocked.apiFetch.mockReset();
  useAppStore.setState({
    user: { id: 'u1' } as never,
    subscription: null,
    subscriptionOwner: null,
    subscriptionLoading: false,
    subscriptionError: null,
  });
});

describe('SM-U5 subscription load failure', () => {
  it('SM-U5: a non-OK response must set subscriptionError, not look like "free"', async () => {
    mocked.apiFetch.mockResolvedValue(new Response('boom', { status: 500 }));
    await useAppStore.getState().fetchSubscription();
    const s = useAppStore.getState();
    // bug: subscription=null AND subscriptionError=null, indistinguishable from free
    expect(s.subscription === null && s.subscriptionError === null).toBe(false);
  });

  it('SM-U5: a failed (non-OK) refetch keeps the last good subscription for the same user', async () => {
    mocked.apiFetch.mockResolvedValueOnce(new Response(JSON.stringify(sub), { status: 200 }));
    await useAppStore.getState().fetchSubscription();
    expect(useAppStore.getState().subscription).toEqual(sub);
    mocked.apiFetch.mockResolvedValueOnce(new Response('boom', { status: 503 }));
    await useAppStore.getState().fetchSubscription();
    expect(useAppStore.getState().subscription).toEqual(sub); // bug: wiped to null
  });

  it('SM-U5: a thrown (network) failure keeps the last good subscription', async () => {
    mocked.apiFetch.mockResolvedValueOnce(new Response(JSON.stringify(sub), { status: 200 }));
    await useAppStore.getState().fetchSubscription();
    mocked.apiFetch.mockRejectedValueOnce(new Error('offline'));
    await useAppStore.getState().fetchSubscription();
    expect(useAppStore.getState().subscription).toEqual(sub); // bug: wiped to null
  });
});
