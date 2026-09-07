import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';
import React from 'react';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => ({
    get: vi.fn(),
    getAll: vi.fn(),
    has: vi.fn(),
    entries: vi.fn(() => []),
    keys: vi.fn(() => []),
    values: vi.fn(() => []),
    toString: vi.fn(() => ''),
    forEach: vi.fn(),
    [Symbol.iterator]: vi.fn(() => [][Symbol.iterator]()),
  }),
  usePathname: () => '/',
  redirect: vi.fn(),
}));

// Mock next/image
vi.mock('next/image', () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  default: (props: any) => {
    // eslint-disable-next-line @next/next/no-img-element
    return React.createElement('img', { ...props, fill: undefined });
  },
}));

// Mock next/head
vi.mock('next/head', () => ({
  default: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock IntersectionObserver
class MockIntersectionObserver {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}
Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  value: MockIntersectionObserver,
});

// Mock ResizeObserver
class MockResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
  unobserve = vi.fn();
}
Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: MockResizeObserver,
});

// Mock scrollTo
Object.defineProperty(window, 'scrollTo', {
  writable: true,
  value: vi.fn(),
});

// Mock localStorage / sessionStorage
//
// Node 25 enabled the Web Storage API by default, and Node 26 makes
// `globalThis.localStorage` evaluate to `undefined` (plus a warning) unless
// `--localstorage-file` is passed. jsdom sees the global already defined and so
// does not install its own, which leaves `createJSONStorage(() => localStorage)`
// in app-store.ts holding `undefined`:
//
//   TypeError: Cannot read properties of undefined (reading 'setItem')
//
// Supplying our own is version-independent — identical behaviour on Node 22,
// where jsdom would have provided one, and on Node 26, where nothing does. The
// alternative, NODE_OPTIONS=--no-webstorage, only fixes CI and leaves anyone
// developing on Node 25+ with the same failure.
//
// Upstream: https://github.com/vitest-dev/vitest/issues/8757
function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(String(key)) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(String(key));
    },
    setItem: (key: string, value: string) => {
      store.set(String(key), String(value));
    },
  } as Storage;
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  // Defined on both: vitest copies jsdom's window keys onto globalThis, but a
  // global Node already owns is left alone, so the two can disagree.
  const storage = createMemoryStorage();
  for (const target of [window, globalThis]) {
    Object.defineProperty(target, name, {
      writable: true,
      configurable: true,
      value: storage,
    });
  }
}
