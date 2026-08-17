import { useSyncExternalStore } from 'react';
import { useReducedMotion } from 'framer-motion';

const subscribe = () => () => {};
const getSnapshot = () => true;
const getServerSnapshot = () => false;

/**
 * `useReducedMotion()` reads matchMedia during render — `null` on the server,
 * the real value on the client. Branching on it directly is a hydration
 * mismatch, so the switch waits until hydration has landed.
 */
export function usePrefersReducedMotion(): boolean {
  const reduced = useReducedMotion();
  const hydrated = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return hydrated && reduced === true;
}
