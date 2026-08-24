# Context: Hooks

## Directory: `ui-next/src/hooks`

## Description
Custom React hooks used to query backend web-sockets and fetch APIs.

## Files
- **`useConversationHistory.test.ts`**: @vitest-environment jsdom
- **`useConversationHistory.ts`**: Code or resource asset facilitating system functionality.
- **`useCredits.ts`**: Reads the caller's credit balance, and optionally their recent ledger.
- **`useFeatureFlags.test.ts`**: @vitest-environment jsdom
- **`useFeatureFlags.ts`**: Code or resource asset facilitating system functionality.
- **`useIsDark.ts`**: Resolved dark-mode flag that is safe to branch on during render.  Two traps this closes, both of which shipped:
- **`useKeyboardShortcuts.ts`**: Command palette: Ctrl/Cmd+K
- **`usePipelineStream.ts`**: Aborts are user-initiated (Stop button, unmount, a new run superseding the old one). The browser surfaces them as a DOMException named 'AbortError' ("signal is aborted without reason"), which must never reach the UI as a
- **`usePrefersReducedMotion.ts`**: `useReducedMotion()` reads matchMedia during render — `null` on the server, the real value on the client. Branching on it directly is a hydration mismatch, so the switch waits until hydration has landed.
- **`usePresets.ts`**: Code or resource asset facilitating system functionality.
- **`useProvenanceCapabilities.ts`**: must gate on this rather than assuming a capability is bound. Fetched once and cached; capabilities don't change within a session.
- **`useQuota.test.ts`**: @vitest-environment jsdom
- **`useQuota.ts`**: Silently ignore quota fetch errors on mount to avoid unhandled rejection
- **`useScrollAnchor.ts`**: Keeps the chat scroll anchored to the bottom as new content arrives.  Smoothness features:
- **`useServerStatus.test.ts`**: @vitest-environment jsdom
- **`useServerStatus.ts`**: Avoid overlapping checks when the backend is slow
- **`useSubscription.ts`**: Shared subscription hook — reads from the Zustand app store. A single fetch is shared across all components (Dashboard, Settings, Composer, UserMenu) to eliminate duplicate API calls.
- **`useWebSocketPipeline.test.ts`**: @vitest-environment jsdom
- **`useWebSocketPipeline.ts`**: Pre-check: is the backend reachable?

## Subfolders
*No subfolders in this directory.*
