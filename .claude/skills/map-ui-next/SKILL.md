---
name: map-ui-next
description: "Folder map of ui-next/ — the Next.js 16 frontend: App Router pages, /api proxy routes to FastAPI, chat and phase components, hooks (SSE stream, WebSocket, IndexedDB), lib (config, markdown, security, docs content), and the Zustand store. Use when changing any UI, proxy route, or client-side data flow."
folders:
  - ui-next/src
---

# ui-next — Folder Map

**Purpose:** Next.js 16 App Router frontend (React 19, TypeScript 5, Tailwind v4, Zustand v5, SWR, IndexedDB). Two halves: the marketing/docs site (static, SEO-tuned, server components) and the chat product (`/chat`, streaming SSE from the FastAPI backend through Next API proxy routes).

## app/ — pages

| File | What it does |
|------|--------------|
| `layout.tsx` | Root layout; `metadataBase`, fonts, providers. |
| `page.tsx` | Home — re-exports `components/landing/LandingPage`. |
| `providers.tsx` | Client providers (theme, auth, SWR). |
| `fonts.ts` | Self-hosted variable fonts (DM Sans, Newsreader, Inconsolata) + `fontVariables`. |
| `error.tsx`, `global-error.tsx`, `not-found.tsx` | Error boundaries and the real-404 handler. |
| `chat/page.tsx` (54KB) | **The product.** Chat surface: run lifecycle, phase accumulation, follow-ups, attachments. Largest file in the app. |
| `chat/page.patterns.test.ts` | Regression guard on phase-push patterns in that page. |
| `dashboard/page.tsx` | Signed-in dashboard. |
| `settings/page.tsx`, `settings/api-keys/page.tsx` (+ layout) | User settings and API-key management (noindex). |
| `login`, `signup`, `forgot-password`, `reset-password` | Auth screens sharing one field-chrome convention. |
| `pricing`, `about`, `contact`, `faq`, `help`, `security`, `privacy`, `terms`, `cookies`, `subprocessors`, `changelog`, `status`, `how-it-works` | Marketing and legal pages, most with a `layout.tsx` supplying metadata (client pages cannot export it). |
| `docs/page.tsx`, `docs/[slug]/page.tsx`, `docs/layout.tsx` | Documentation index and dynamic doc pages; content from `lib/docs.ts`. |
| `landing/page.tsx` | Permanent redirect to `/` (was a duplicate URL splitting ranking signals). |
| `robots.ts`, `sitemap.ts` | `robots.txt` and `sitemap.xml`. |
| `llms.txt/route.ts`, `llms-full.txt/route.ts` | Machine-readable site index and full docs corpus for AI answer engines. |
| `status/StatusClient.tsx` | Client half of the status page. |

## app/api/ — proxy routes to the FastAPI backend

Each route forwards to the backend with CSRF and auth handling. Every entry in `lib/config.ts` `API.*` needs a matching route file or the call 404s.

| Route | Backend target |
|-------|----------------|
| `run/`, `run-followup/`, `stop/` | Pipeline start (SSE), follow-up, cancel. |
| `agent/run/`, `agent/run/sync/` | Bearer-key agent endpoints. |
| `gate/`, `estimate/`, `presets/`, `models/`, `health/` | Routing decision, cost estimate, catalogue, health. |
| `search/`, `upload/`, `generate-image/` | Search, file upload, image generation. |
| `csrf/` | CSRF token issue. |
| `websocket/ticket/` | Short-lived WebSocket ticket. |
| `credits/`, `credits/ledger/`, `quota/` | Balance, ledger, quota. |
| `billing/checkout`, `billing/portal`, `billing/subscription`, `billing/webhook`, `billing/paypal/webhook` | Stripe and PayPal. |
| `account/api-keys/`, `account/api-keys/[id]/`, `account/delete/` | Key CRUD (UUID-validated) and account deletion. |
| `neuro/recall`, `neuro/learn`, `neuro/health`, `neuro/sessions` | Memory engine. |
| `provenance/capabilities`, `inspect`, `scrub`, `rewrite` | Watermark inspect/scrub; rewrite returns 501 until Layer B is bound. |
| `feedback/`, `error-report/` | Feedback and client error reporting. |
| `weather/`, `stocks/`, `calculate/` | Legacy widgets. |

## components/

| Group | Files |
|-------|-------|
| `chat/` | `ChatFeed.tsx` (33KB, message + phase list), `ChatMessage.tsx`, `MarkdownRenderer.tsx` (+ patterns test), `StreamingMarkdown.tsx` (finalized content only, not live SSE), `CodeBlock.tsx` (lazy Prism chunk), `ErrorMessage.tsx`, `MethodChoicePrompt.tsx`, `PipelineSkeleton.tsx`, `ManifestationVisuals.tsx`, `ChatErrorBoundary.tsx`. |
| `phases/` | `PhaseRenderer.tsx` (24KB, the per-phase dispatcher), `PhaseCard.tsx` (shared chrome, `formatModelLabel`, `formatDurationMs`), `ClassificationCard`, `CritiqueCard`, `SynthesisCard`, `SynthesisRenderer`, `SourceCard`, `ResearchProgress`. |
| `layout/` | `Sidebar.tsx` (24KB), `Composer.tsx` (21KB), `SiteHeader`, `SiteFooter`, `CommandPalette`, `PhaseTimeline`, `NeuroPanel`, `SecurityModal` / `SecurityBadge`, `ShortcutModal`, `UpgradeModal`, `UserMenu`, `UsageBadge`. |
| `landing/` | `LandingPage.tsx` (27KB) and `Testimonial.tsx` (renders nothing while empty, by design). |
| `run-record/` | The landing page's real-run exhibit: `RunRecord.tsx` (25KB), `RunIndex`, `ScoreMatrix`, `ApparatusToggle`, `Segments`. |
| `docs/` | `DocMarkdown.tsx`, `DocsSidebar.tsx` — server components so every doc URL is a real anchor. |
| `provenance/` | `EgressSettings`, `ProvenanceBadge`, `ProvenanceReport`. |
| `widgets/` | `WidgetRenderer` plus `WeatherWidget`, `StockWidget`, `CalculationWidget`. |
| `ui/` | `Button`, `Badge`, `Spinner`, `Tooltip`, `ThemeToggle`, `ProfessionalRenderer`, `index.ts` barrel. |
| `brand/`, `seo/`, `not-found/` | `Logo` / `LogoMark`, `JsonLd`, `NotFoundView`. |

## hooks/

| File | What it does |
|------|--------------|
| `usePipelineStream.ts` | **The SSE run hook** — starts a run, reads frames, exposes `PipelineError`. |
| `useWebSocketPipeline.ts` | WebSocket live updates with connection status and reconnect. |
| `useConversationHistory.ts` | IndexedDB-backed conversation list. |
| `useCredits.ts`, `useQuota.ts`, `useSubscription.ts` | Billing and usage reads via SWR. |
| `usePresets.ts`, `useServerStatus.ts`, `useProvenanceCapabilities.ts` | Catalogue and status reads. |
| `useKeyboardShortcuts.ts`, `useScrollAnchor.ts` | Chat UX. |
| `useIsDark.ts`, `usePrefersReducedMotion.ts` | Hydration-safe media/theme flags; never branch on raw `matchMedia` during render. |
| `useFeatureFlags.ts` | `isEnabled`, `setEnabled`, `resetFlags`. |
| `*.test.ts` | jsdom tests for history, quota, flags, server status, WebSocket. |

## lib/

| File | What it does |
|------|--------------|
| `config.ts` (13KB) | `API` endpoint map, `METHOD_PHASES`, `METHOD_DESCRIPTIONS`, `EXAMPLE_PROMPTS`, `DEFAULTS`. |
| `api-client.ts` | Browser fetch wrapper (`apiFetch`, `fetchGateDecision`, cache clear). |
| `api-proxy.ts` | `proxyJson` — shared server-side helper for the `/api` routes. |
| `server-config.ts` | Backend base URL, WebSocket host/port allowlist. |
| `sse-reader.ts` | `readSSEStream` over a `ReadableStream`. |
| `markdown.ts` (51KB) | `buildMarkdownFromPhase(s)` — renders backend phase payloads into markdown; paired with an 11KB edge-case test. |
| `types.ts` | Shared types: `MethodId`, `PhaseEvent`, `Attachment`, provenance types. |
| `db.ts` | IndexedDB conversation store. |
| `conversation-history.ts` | Conversation-to-message mapping. |
| `security-server.ts` (18KB) | Server-side validation, CSRF sign/verify, `VALIDATION_LIMITS`. |
| `security-client.ts`, `security-constants.ts`, `security-csp.ts` | Client CSRF fetch, cookie/header names, CSP builder. |
| `auth.ts`, `supabase.ts` | Session helpers and Supabase client. |
| `docs.ts` (53KB) | The documentation corpus: `DOCS`, `DOC_SECTIONS`, `DOC_SLUGS`, `getDoc`. |
| `faq.ts`, `changelog.ts`, `method-hints.tsx` | Static content registries. |
| `demo-record.ts`, `image-showcase.ts` | The real captured run and image run the landing page counts its figures from. |
| `route-suggestions.ts` | 404 route recovery: `NAVIGABLE_ROUTES`, `FEATURED_ROUTES`. |
| `site.ts`, `schema.ts` | Canonical site identity, absolute URLs, schema.org builders. |
| `provenance.ts` | Extracts the provenance report from a synthesis SSE payload. |
| `capabilities.generated.ts` | **Auto-generated** by `scripts/update_mindmap_meta.py` on each commit — never hand-edit. |
| `error-reporting.ts`, `utils.ts` | Sentry plus backend error reporting; `cn`, `esc`, clipboard. |
| `claims.test.ts` | Guards public pages against unbacked trust/compliance claims. |

## stores/, proxy, test

| File | What it does |
|------|--------------|
| `stores/app-store.ts` | Zustand global state with persistence and migration (`useAppStore`, `ComposerAttachment`, `Tier`). |
| `proxy.ts` | Middleware-level proxy (`proxy`, `config` matcher); CSRF gating for POST routes. |
| `test/setup.ts`, `test/utils.tsx` | Vitest setup, `renderWithProviders`, mock factories. |

## Key entry points & gotchas

- **Tailwind v4 is CSS-native.** Config lives in `globals.css` via `@import "tailwindcss"`. Do not create `tailwind.config.ts`.
- **Run the dev server locally** (`npm run dev`). A production build blocks the localhost backend via the SSRF guard, and stale builds 404 new routes.
- Every `API.*` constant in `lib/config.ts` needs a matching `src/app/api/*/route.ts`, or the call 404s. POST routes are CSRF-gated through `proxy.ts`.
- `capabilities.generated.ts` is rewritten by a post-commit hook — edit the generator, not the file.
- Client pages cannot export `metadata`; add a sibling `layout.tsx`, the pattern used across marketing pages.
- `StreamingMarkdown` is for finalized content only; live SSE text goes through the chat feed's streaming path.
- The SSE payload shape comes from `application/services/serializers.py` on the backend — changes there land in `lib/markdown.ts` and `components/phases/PhaseRenderer.tsx`.
