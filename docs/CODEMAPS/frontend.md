<!-- Generated: 2026-06-26 | Files scanned: 416 | Token estimate: ~800 -->

# Frontend Structure — Reasoner (Next.js 16 / React 19 / TypeScript 5)

## Project Layout

```
ui-next/src/
├── app/                          # Next.js 16 App Router
│   ├── layout.tsx                # Root layout, providers, global styles
│   ├── page.tsx                  # Home page (landing/redirect)
│   ├── providers.tsx             # AppProvider wrapper (Zustand, SWR, auth)
│   ├── error.tsx                 # Global error boundary
│   ├── not-found.tsx             # 404 handler
│   │
│   ├── chat/                     # Chat interface
│   │   ├── page.tsx              # Main chat surface
│   │   └── layout.tsx            # Chat-specific layout
│   │
│   ├── dashboard/                # User dashboard
│   │   ├── page.tsx              # Dashboard home
│   │   └── layout.tsx
│   │
│   ├── settings/                 # Settings pages
│   │   ├── page.tsx              # Account settings
│   │   ├── security/page.tsx     # Security settings
│   │   ├── billing/page.tsx      # Subscription management
│   │   └── preferences/page.tsx  # User preferences
│   │
│   ├── (auth)/                   # Auth route group
│   │   ├── login/page.tsx        # Login page
│   │   ├── signup/page.tsx       # Sign-up page
│   │   ├── forgot-password/page.tsx
│   │   ├── reset-password/page.tsx
│   │   └── verify-email/page.tsx
│   │
│   ├── (landing)/                # Landing pages
│   │   ├── landing/page.tsx      # Main landing
│   │   ├── about/page.tsx        # About page
│   │   ├── faq/page.tsx          # FAQ
│   │   ├── contact/page.tsx      # Contact form
│   │   ├── terms/page.tsx        # Terms of service
│   │   ├── privacy/page.tsx      # Privacy policy
│   │   ├── cookies/page.tsx      # Cookie policy
│   │   ├── security/page.tsx     # Security info
│   │   ├── help/page.tsx         # Help center
│   │   └── blog/page.tsx         # Blog listing
│   │
│   └── api/                      # Next.js API routes (SSE proxies)
│       ├── run/route.ts          # POST /api/run (proxy to backend /pipelines/run)
│       ├── run-followup/route.ts # POST /api/run-followup
│       ├── stop/route.ts         # POST /api/stop
│       ├── cache/route.ts        # GET /api/cache (cached results)
│       ├── presets/route.ts      # GET /api/presets (preset list + cost)
│       ├── estimate/route.ts     # POST /api/estimate (cost estimation)
│       ├── upload/route.ts       # POST /api/upload (file upload)
│       ├── csrf/route.ts         # GET /api/csrf (CSRF token)
│       ├── weather/route.ts      # GET /api/weather (widget)
│       ├── stocks/route.ts       # GET /api/stocks (widget)
│       ├── calculate/route.ts    # POST /api/calculate (widget)
│       ├── feedback/route.ts     # POST /api/feedback
│       ├── generate-image/route.ts # POST /api/generate-image (image generation)
│       ├── search/route.ts       # GET /api/search (search functionality)
│       ├── neuro/
│       │   ├── recall/route.ts   # POST /api/neuro/recall (memory retrieval)
│       │   └── learn/route.ts    # POST /api/neuro/learn (memory storage)
│       └── proxy.ts              # HTTP proxy utilities
│
├── components/                   # React components (100+)
│   ├── chat/                     # Chat-specific components
│   │   ├── ChatFeed.tsx          # Main scrollable message feed
│   │   ├── ChatMessage.tsx       # Single message renderer with context menu
│   │   ├── MarkdownRenderer.tsx  # Markdown + GFM rendering (react-markdown)
│   │   ├── CodeBlock.tsx         # Syntax-highlighted code blocks (react-syntax-highlighter)
│   │   ├── TypewriterMarkdown.tsx # Streaming text animation
│   │   ├── ErrorMessage.tsx      # Error display with retry
│   │   ├── ChatErrorBoundary.tsx # Error boundary for chat
│   │   └── ManifestationVisuals.tsx # Visual effects for phase completion
│   │
│   ├── layout/                   # Layout components
│   │   ├── SiteHeader.tsx        # Top navigation bar
│   │   ├── Sidebar.tsx           # Left sidebar (chat history)
│   │   ├── Composer.tsx          # Input composer + preset selector
│   │   ├── PhaseTimeline.tsx     # Visual phase progress (0-5)
│   │   ├── CommandPalette.tsx    # Cmd+K global command palette
│   │   ├── ShortcutModal.tsx     # Keyboard shortcuts help (?)
│   │   ├── UserMenu.tsx          # User profile menu (dropdown)
│   │   ├── UpgradeModal.tsx      # Subscription upgrade prompt
│   │   ├── SecurityModal.tsx     # Security info modal
│   │   ├── NeuroPanel.tsx        # Memory/Neuro management panel
│   │   ├── UsageBadge.tsx        # Quota/usage indicator
│   │   ├── SecurityBadge.tsx     # Security status indicator
│   │   ├── BlobBackground.tsx    # Animated blob visual
│   │   ├── NebulaBackground.tsx  # Nebula/starfield background
│   │   ├── ThreeBackground.tsx   # 3D Three.js background
│   │   ├── NeuralConstellation.tsx # Neural network visualization
│   │   └── BackgroundBlobs.tsx   # Animated background elements
│   │
│   ├── phases/                   # Phase-specific renderers
│   │   ├── PhaseCard.tsx         # Generic phase container
│   │   ├── PhaseRenderer.tsx     # Dispatch to phase-specific renderers
│   │   ├── ClassificationCard.tsx # Phase 0 (task_type, language, complexity)
│   │   ├── CritiqueCard.tsx      # Phase 3 (scored candidates)
│   │   ├── SynthesisRenderer.tsx # Phase 5 (final solution + blueprint)
│   │   ├── DebatePhaseRenderer.tsx # Method-specific: Debate
│   │   ├── JuryPhaseRenderer.tsx  # Method-specific: Jury
│   │   ├── ResearchPhaseRenderer.tsx # Method-specific: Research
│   │   └── [method-specific]    # Other methods (Scientific, Socratic, etc.)
│   │
│   ├── ui/                       # Headless UI primitives
│   │   ├── Button.tsx            # Styled button (primary, secondary, ghost, etc.)
│   │   ├── Badge.tsx             # Status/method badges
│   │   ├── Spinner.tsx           # Loading spinner
│   │   ├── ThemeToggle.tsx       # Light/dark mode toggle
│   │   ├── Tooltip.tsx           # Tooltip primitive (Radix UI)
│   │   └── index.ts              # Export barrel
│   │
│   ├── widgets/                  # Interactive widgets
│   │   ├── WidgetRenderer.tsx    # Widget dispatcher (routes by type)
│   │   ├── CalculationWidget.tsx # Math calculator display
│   │   ├── StockWidget.tsx       # Stock quote display
│   │   ├── WeatherWidget.tsx     # Weather display
│   │   └── ManifestationVisuals.tsx # Visual effects
│   │
│   ├── landing/                  # Landing page components
│   │   ├── LandingPage.tsx       # Main landing page
│   │   ├── Hero.tsx              # Hero section
│   │   ├── BentoGrid.tsx         # Feature grid (bento layout)
│   │   ├── LandingFooter.tsx     # Landing footer
│   │   └── CTASection.tsx        # Call-to-action sections
│   │
│   └── brand/                    # Branding components
│       └── Logo.tsx              # Logo component
│
├── hooks/                        # React hooks (20+)
│   ├── usePipelineStream.ts      # **CORE** SSE handler (streaming phases)
│   ├── useConversationHistory.ts # Chat history (IndexedDB + API)
│   ├── usePresets.ts             # Fetch presets + cost estimation
│   ├── useQuota.ts               # User quota tracking
│   ├── useSubscription.ts        # Subscription status + tier
│   ├── useKeyboardShortcuts.ts   # Cmd+K, Shift+Enter, Esc handlers
│   ├── useServerStatus.ts        # Backend health check
│   ├── useScrollAnchor.ts        # Auto-scroll to latest message
│   ├── useFeatureFlags.ts        # Feature flag management
│   ├── useReducedMotion.ts       # Accessibility: prefers-reduced-motion
│   └── [other hooks]             # Navigation, auth, theme, etc.
│
├── lib/                          # Utility libraries & helpers
│   ├── api-client.ts             # HTTP client wrapper (fetch-based)
│   ├── db.ts                     # IndexedDB wrapper via `idb` v8
│   ├── security-server.ts        # Server-side: CSRF validation, auth headers
│   ├── security-client.ts        # Client-side: CSRF token, secure storage
│   ├── security-constants.ts     # Security-related constants
│   ├── conversation-history.ts   # Local chat history storage (IndexedDB)
│   ├── sse-reader.ts             # SSE stream parsing (ReadableStream)
│   ├── utils.ts                  # General utilities (classnames, formatters)
│   ├── types.ts                  # TypeScript interfaces (Message, Phase, etc.)
│   ├── markdown.ts               # Markdown parsing utilities
│   ├── design-tokens.ts          # CSS design tokens (colors, spacing, durations)
│   ├── method-colors.ts          # Method → color mapping (visual consistency)
│   ├── method-hints.tsx          # Method name → description mapping
│   ├── supabase.ts               # Supabase client (if used)
│   └── [other utilities]         # Formatting, validation, etc.
│
└── stores/                       # Zustand state management
    ├── app-store.ts             # **CORE** Global app state (persisted to localStorage)
    │                            # - currentConversationId, messages, currentPhase
    │                            # - isStreaming, selectedPreset, userQuota, theme
    └── [method-specific]        # Optional method-specific stores
```

## Component Hierarchy (Visual Tree)

```
<RootLayout>
  ├─ <meta> (head metadata)
  │
  ├─ <Providers>
  │  ├─ AuthProvider
  │  ├─ ZustandProvider
  │  └─ SWRConfig
  │
  ├─ <SiteHeader>
  │  ├─ <Logo />
  │  ├─ <nav>
  │  │  ├─ Home link
  │  │  ├─ Pricing link
  │  │  ├─ Docs link
  │  │  └─ GitHub link
  │  ├─ <UserMenu>
  │  │  ├─ Profile link
  │  │  ├─ Settings link
  │  │  ├─ Logout button
  │  │  └─ [admin section]
  │  └─ <ThemeToggle />
  │
  ├─ {page content}
  │
  ├─ <ChatPage> (on /chat)
  │  ├─ <Sidebar>
  │  │  ├─ <Button> New chat
  │  │  └─ <ChatListItem>[] (past conversations)
  │  │
  │  ├─ <MainContent>
  │  │  ├─ <ChatFeed>
  │  │  │  ├─ <ChatMessage>[]
  │  │  │  │  ├─ <MarkdownRenderer> (for text)
  │  │  │  │  ├─ <CodeBlock> (for code)
  │  │  │  │  ├─ <PhaseCard> (for phases)
  │  │  │  │  └─ <WidgetRenderer> (for widgets)
  │  │  │  └─ Auto-scroll anchor
  │  │  │
  │  │  ├─ <PhaseTimeline>
  │  │  │  └─ <PhaseIndicator>[] (0, 1, 2, 3, 4, 5)
  │  │  │
  │  │  └─ <Composer>
  │  │     ├─ <TextArea>
  │  │     ├─ <PresetSelector>
  │  │     │  └─ <PresetButton>[]
  │  │     ├─ <AttachButton>
  │  │     └─ <SendButton>
  │  │
  │  └─ <Modals>
  │     ├─ <ShortcutModal> (? to open)
  │     ├─ <CommandPalette> (Cmd+K)
  │     ├─ <SecurityModal>
  │     ├─ <UpgradeModal>
  │     └─ <NeuroPanel>
  │
  └─ <Portals>
     └─ <Toast notifications>
```

## Key Hooks (Core SSE Integration)

### `usePipelineStream()` — Main Streaming Handler

```typescript
// Parses SSE events from backend
usePipelineStream({
  problem: string
  preset?: string
  onProgress?: (phase: number) => void
  onComplete?: (state: PipelineState) => void
})

// Handles:
// - Connection management
// - SSE event parsing
// - Phase updates
// - Error recovery
// - Retry logic
// - Token accumulation
```

### `useConversationHistory()` — Chat History

```typescript
// Load/save past conversations
useConversationHistory({
  conversationId?: string
  limit?: number
})

// Manages:
// - IndexedDB persistence
// - API sync
// - Loading states
```

### `usePresets()` — Preset Listing

```typescript
// Fetch available presets + cost estimation
usePresets()

// Returns:
// - presets: {id, name, cost, method, tier}[]
// - isLoading: boolean
// - error?: Error
```

## State Management (Zustand + SWR)

### Global State (`app-store.ts`)

```typescript
interface AppStore {
  // Chat state
  currentConversationId: string
  messages: Message[]
  currentPhase: number
  isStreaming: boolean
  
  // User preferences
  selectedPreset: string
  theme: 'light' | 'dark'
  sidebarCollapsed: boolean
  
  // User data
  userQuota: Quota
  user?: User
  
  // Actions
  addMessage(msg: Message): void
  updatePhase(phaseNum: number): void
  setTheme(theme: 'light' | 'dark'): void
  reset(): void
}
```

### Server State (SWR hooks)

- Presets (rarely changes)
- User quota (refreshed per message)
- Server health (background check)
- Conversation history (pagination)

## Styling (Tailwind CSS v4)

**NO `tailwind.config.ts`** — Tailwind v4 uses CSS-native configuration

**Entry:** `ui-next/src/globals.css`
```css
@import "tailwindcss";  /* Includes base, components, utilities */

:root {
  --color-bg: oklch(98% 0 0);
  --color-text: oklch(18% 0 0);
  --color-accent: oklch(68% 0.21 250);
  --method-debate-rgb: 239, 68, 68;      /* Red */
  --method-jury-rgb: 59, 130, 246;       /* Blue */
  /* ... more method colors ... */
}
```

**Design Tokens:**
- Colors, spacing, typography via CSS custom properties
- Motion: `--duration-fast: 150ms`, `--duration-normal: 300ms`
- Shadows, borders, radii via Tailwind utilities

## API Routes (Next.js Proxies)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/run` | POST | Proxy to `/pipelines/run` (SSE) |
| `/api/run-followup` | POST | Follow-up turn (SSE) |
| `/api/presets` | GET | List presets + cost |
| `/api/estimate` | POST | Pre-estimate cost/tokens |
| `/api/csrf` | GET | CSRF token generation |
| `/api/upload` | POST | File upload proxy |
| `/api/stocks` | GET | Stock widget proxy |
| `/api/weather` | GET | Weather widget proxy |
| `/api/calculate` | POST | Calculator widget proxy |
| `/api/neuro/recall` | POST | Memory recall proxy |
| `/api/neuro/learn` | POST | Memory learn proxy |

## Key Patterns

### SSE Message Handling

```typescript
const response = await fetch('/api/run', {
  method: 'POST',
  body: JSON.stringify({problem, preset}),
  signal: abortController.signal
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const {done, value} = await reader.read()
  if (done) break
  
  const chunk = decoder.decode(value)
  const lines = chunk.split('\n')
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6))
      store.updatePhase(event.phase)
      // ... handle event
    }
  }
}
```

### CSRF Protection

1. GET `/api/csrf` → receive token
2. Include in POST request header: `X-CSRF-Token: ...`
3. Backend validates signature

### Theme Persistence

```typescript
// Zustand persists theme to localStorage
// On mount: read localStorage, apply to <html class="dark">
// On change: update localStorage + DOM
```

## Performance Optimizations

- **Code splitting:** Dynamic imports for heavy components
- **Image optimization:** Next.js Image component
- **Virtual scrolling:** Long chat feeds
- **Memoization:** useMemo/useCallback to prevent unnecessary renders
- **Web Workers:** Expensive computations (if needed)

## Accessibility Features

- Semantic HTML (`<header>`, `<nav>`, `<main>`, `<footer>`)
- ARIA labels for interactive elements
- Keyboard shortcuts (Cmd+K, Shift+Enter, Escape)
- Color contrast (WCAG AA+)
- Reduced motion support (`prefers-reduced-motion`)
- Focus management (trap in modals)

## Testing Strategy

- **Unit:** Component logic (hooks, utilities)
- **Integration:** SSE + state management
- **E2E:** User flows (login → chat → preset selection → streaming)
- **Visual regression:** Screenshots at key breakpoints (320, 768, 1024, 1440)
