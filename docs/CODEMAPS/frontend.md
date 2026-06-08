<!-- Generated: 2026-06-08 | Files scanned: 375 | Token estimate: ~800 -->

# Frontend Architecture (ui-next/)

## Framework
Next.js 16 · App Router · React 19 · TypeScript 5 · Tailwind CSS v4
**Note:** Tailwind v4 is CSS-native — NO tailwind.config.ts. Use `@import "tailwindcss"` in globals.css.

## Page Tree
```
app/
├─ page.tsx              → root redirect (→ /landing or /chat)
├─ layout.tsx            → root layout + providers
├─ providers.tsx          → ThemeProvider, Zustand hydration
├─ chat/page.tsx         → PRIMARY chat interface
├─ landing/page.tsx      → landing page shell
├─ dashboard/page.tsx    → user dashboard
├─ login/page.tsx        → auth - login
├─ signup/page.tsx       → auth - register
├─ forgot-password/      → auth - reset flow
├─ reset-password/       → auth - reset confirm
├─ settings/page.tsx     → user settings
├─ pricing/page.tsx      → pricing + Stripe checkout
├─ about/ contact/ faq/ help/ cookies/ privacy/ terms/
└─ error.tsx             → error boundary
```

## Component Hierarchy
```
components/
├─ chat/
│   ├─ ChatFeed.tsx          → message list, scroll anchor
│   ├─ ChatMessage.tsx       → individual message with phase cards
│   ├─ MarkdownRenderer.tsx  → react-markdown + code highlighting
│   ├─ TypewriterMarkdown.tsx → streaming typewriter effect
│   ├─ CodeBlock.tsx         → syntax-highlighted code
│   ├─ ErrorMessage.tsx      → error state UI
│   ├─ ManifestationVisuals.tsx → visual effects
│   └─ ChatErrorBoundary.tsx → React error boundary
├─ layout/
│   ├─ Composer.tsx          → input bar, preset selector, submit
│   ├─ Sidebar.tsx           → history sidebar
│   ├─ PhaseTimeline.tsx     → live phase progress indicator
│   ├─ NeuroPanel.tsx        → Neuro LTM panel
│   ├─ CommandPalette.tsx    → Cmd+K command palette
│   ├─ ShortcutModal.tsx     → keyboard shortcut reference
│   ├─ SiteHeader.tsx        → top nav
│   ├─ SiteFooter.tsx        → footer
│   ├─ UserMenu.tsx          → avatar / account dropdown
│   ├─ UsageBadge.tsx        → quota display
│   ├─ UpgradeModal.tsx      → paywall modal
│   └─ ThreeBackground.tsx   → Three.js animated background
├─ phases/
│   ├─ PhaseRenderer.tsx     → routes phase data to correct card
│   ├─ PhaseCard.tsx         → generic collapsible phase container
│   ├─ ClassificationCard.tsx → Phase 0 display
│   ├─ CritiqueCard.tsx      → Phase 3 critique display
│   └─ SynthesisCard.tsx     → Phase 5 synthesis + epistemic labels
├─ widgets/
│   ├─ WidgetRenderer.tsx    → dispatch to specific widget
│   ├─ StockWidget.tsx       → stock price + chart
│   ├─ WeatherWidget.tsx     → weather data
│   └─ CalculationWidget.tsx → math result display
├─ landing/
│   ├─ LandingPage.tsx       → landing page composition (app/landing/page.tsx delegates here)
│   ├─ Hero.tsx              → hero section
│   ├─ BentoGrid.tsx         → feature bento grid
│   └─ LandingFooter.tsx
├─ fx/BackgroundBlobs.tsx    → CSS blob animations
└─ ui/
    ├─ Button.tsx Badge.tsx Spinner.tsx Tooltip.tsx ThemeToggle.tsx
    └─ index.ts
```

## State Management
```
stores/app-store.ts (Zustand v5 + IndexedDB persistence)
  ├─ conversations[]       → full conversation history
  ├─ activeConversationId
  ├─ currentPreset         → selected reasoning method/preset
  ├─ sidebarOpen / theme
  └─ hydrated              → IndexedDB hydration flag

lib/db.ts                  → IndexedDB via `idb` v8
lib/conversation-history.ts → persistence helpers
```

## Hooks
```
hooks/usePipelineStream.ts       → SSE event parsing, phase state assembly
hooks/useWebSocketPipeline.ts    → WebSocket pipeline alternative
hooks/useConversationHistory.ts  → CRUD on conversation store
hooks/useServerStatus.ts         → backend health polling (SWR)
hooks/usePresets.ts              → preset list from /api/presets
hooks/useQuota.ts                → quota from /api/quota
hooks/useSubscription.ts         → subscription status
hooks/useFeatureFlags.ts         → feature gate checks
hooks/useKeyboardShortcuts.ts    → global keyboard bindings
hooks/useScrollAnchor.ts         → chat auto-scroll
```

## Test Files (Vitest)
```
app/chat/page.patterns.test.ts
app/globals.css.test.ts
components/chat/MarkdownRenderer.patterns.test.ts
components/layout/NeuroPanel.patterns.test.ts
hooks/useConversationHistory.test.ts
hooks/useFeatureFlags.test.ts
hooks/useQuota.test.ts
hooks/useServerStatus.test.ts
lib/conversation-history.test.ts
lib/security-client.patterns.test.ts
lib/security-server.test.ts
stores/app-store.migrate.test.ts
```

## Lib / Utilities
```
lib/api-client.ts        → typed fetch wrappers for backend
lib/sse-reader.ts        → SSE stream reader
lib/auth.ts              → Supabase auth helpers
lib/supabase.ts          → Supabase client init
lib/security-client.ts   → CSRF token management (client)
lib/security-server.ts   → CSRF validation (Next.js API routes)
lib/markdown.ts          → markdown processing utilities
lib/types.ts             → shared TypeScript types
lib/method-hints.tsx     → method description copy
lib/config.ts            → env-based config
lib/animation-cache.ts   → animation frame caching
```
