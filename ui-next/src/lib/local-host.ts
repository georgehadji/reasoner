'use client';

import { useSyncExternalStore } from 'react';

/** True for a local development host: localhost, *.localhost, 127.0.0.1, ::1. */
export function isLocalHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return (
    host === 'localhost' ||
    host.endsWith('.localhost') ||
    host === '127.0.0.1' ||
    host === '::1' ||
    host === '[::1]'
  );
}

const noSubscribe = () => () => {};

/**
 * Whether the app is being served from this machine, where it runs without
 * sign-in (ALLOW_ANONYMOUS_RUNS). False during server rendering and
 * hydration, so the first client render matches the server's HTML.
 */
export function useIsLocalHost(): boolean {
  return useSyncExternalStore(
    noSubscribe,
    () => isLocalHost(window.location.hostname),
    () => false,
  );
}
