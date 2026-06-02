# Graph Report - ui-next  (2026-05-08)

## Corpus Check
- 165 files · ~64,809 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 601 nodes · 679 edges · 67 communities detected
- Extraction: 82% EXTRACTED · 18% INFERRED · 0% AMBIGUOUS · INFERRED: 124 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 176|Community 176]]
- [[_COMMUNITY_Community 177|Community 177]]

## God Nodes (most connected - your core abstractions)
1. `POST()` - 43 edges
2. `GET()` - 27 edges
3. `handleSubmit()` - 14 edges
4. `fetchJSON()` - 12 edges
5. `fetchWithCsrf()` - 12 edges
6. `DELETE()` - 10 edges
7. `getDB()` - 9 edges
8. `Globe SVG Icon` - 9 edges
9. `isEnabled()` - 8 edges
10. `toAuthError()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `POST()` --calls--> `Error()`  [INFERRED]
  E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\api\upload\route.ts → E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\error.tsx
- `signInWithOAuth()` --calls--> `Error()`  [INFERRED]
  E:\Documents\Vibe-Coding\Reasoner\ui-next\src\lib\auth.ts → E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\error.tsx
- `LoginMessage()` --calls--> `GET()`  [INFERRED]
  E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\login\page.tsx → E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\api\weather\route.ts
- `loadConversation()` --calls--> `GET()`  [INFERRED]
  E:\Documents\Vibe-Coding\Reasoner\ui-next\src\lib\db.ts → E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\api\weather\route.ts
- `deleteConversation()` --calls--> `DELETE()`  [INFERRED]
  E:\Documents\Vibe-Coding\Reasoner\ui-next\src\lib\db.ts → E:\Documents\Vibe-Coding\Reasoner\ui-next\src\app\api\cache\route.ts

## Communities

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (25): buildConnectSrc(), proxy(), DELETE(), GET(), POST(), _evictExpiredRateLimitBuckets(), generateCsrfToken(), generateSignedCsrfToken() (+17 more)

### Community 1 - "Community 1"
Cohesion: 0.2
Nodes (21): apiFetch(), _calculate(), clearCache(), fetchJSON(), fetchPresets(), _fetchStocks(), _fetchWeather(), formatApiError() (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.17
Nodes (18): MemoryBadge(), AttachButton(), autoResize(), clearFileError(), formatFileSize(), handleDragLeave(), handleDragOver(), handleDrop() (+10 more)

### Community 3 - "Community 3"
Cohesion: 0.12
Nodes (11): ChatErrorBoundary, Error(), reportError(), withErrorReporting(), handleFeedback(), createMockMessage(), createMockPhase(), createMockPipelineState() (+3 more)

### Community 4 - "Community 4"
Cohesion: 0.1
Nodes (7): conversationToMessages(), buildMarkdownFromPhase(), buildMarkdownFromPhases(), handleClearCache(), handleLoad(), handleResume(), readSSEStream()

### Community 5 - "Community 5"
Cohesion: 0.23
Nodes (14): getAuthToken(), getCurrentUser(), getEnabledOAuthProviders(), getSession(), guardSupabase(), signInWithEmail(), signInWithOAuth(), signOut() (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.22
Nodes (8): AppleIcon(), GitHubIcon(), GoogleIcon(), handleContinueGenerating(), handleOAuth(), handleSubmit(), isValidEmail(), LoginMessage()

### Community 7 - "Community 7"
Cohesion: 0.15
Nodes (10): handleCopy(), handleFeedback(), handleCopy(), handleCopy(), isWarningContent(), parseErrorMessage(), cn(), copyToClipboard() (+2 more)

### Community 8 - "Community 8"
Cohesion: 0.33
Nodes (9): getDuration(), getModels(), getQuality(), getSubagents(), getSynthesisHighlights(), getSynthesisSections(), getTokens(), getVettedContext() (+1 more)

### Community 9 - "Community 9"
Cohesion: 0.2
Nodes (11): Earth Globe Symbol, Dark Gray Fill Color (#666), Latitude and Longitude Grid Lines, Globe SVG Icon, Internationalization Feature, Monochrome Icon Design, Reasoner Next.js Frontend, Static Web Asset (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.51
Nodes (8): clearAllConversations(), deleteConversation(), getDB(), loadAllConversations(), loadConversation(), loadConversationsByThread(), loadConversationsPage(), saveConversation()

### Community 11 - "Community 11"
Cohesion: 0.24
Nodes (10): Next.js Breaking Changes Warning, API Proxy Pattern, Authentication Flow (Pass-Through Proxy), Dual-Stream Frontend, IndexedDB Browser Persistence, PhaseDispatcher, usePipelineStream (SSE Streaming Hook), Zustand Client State (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.43
Nodes (6): cn(), getPrefersReducedMotion(), getPrefersReducedMotionServer(), subscribePrefersReducedMotion(), useMounted(), usePrefersReducedMotion()

### Community 13 - "Community 13"
Cohesion: 0.46
Nodes (6): createMaterial(), generateNodes(), initLineGeo(), initParticleGeo(), onMove(), seededRandom()

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (8): Dark Theme Aesthetic, Dot Mark, Apple Touch Icon, iOS Web App Touch Icon, Minimalist Design, Next.js Public Static Directory, Reasoner Brand Identity, Stylized R Letterform

### Community 15 - "Community 15"
Cohesion: 0.36
Nodes (8): Document Symbol, Folded Corner Page Indicator, Gray Color #666, Minimalist Icon Design, Public Static Asset, File SVG Icon, Text Content Lines, ui-next Next.js Frontend

### Community 16 - "Community 16"
Cohesion: 0.33
Nodes (7): CQRS, Event Sourcing, Hexagonal Architecture, HyperGate Pre-Routing, Mixin Pattern, Provider Router with Fallbacks, 17 Reasoning Methods

### Community 17 - "Community 17"
Cohesion: 0.29
Nodes (7): Vercel, Hosting Platform, Vercel Logo, Next.js, SVG Format, Triangle, White

### Community 18 - "Community 18"
Cohesion: 0.6
Nodes (4): ChartSkeleton(), isValidPortalUrl(), openPortal(), StatCardSkeleton()

### Community 19 - "Community 19"
Cohesion: 0.33
Nodes (2): UsageBadge(), useQuota()

### Community 20 - "Community 20"
Cohesion: 0.47
Nodes (3): getDevErrorMessage(), PipelineError, usePipelineStream()

### Community 21 - "Community 21"
Cohesion: 0.4
Nodes (6): Stroke Border (currentColor), Reasoner Brand Identity, Dark Rounded Background (#1F1F1F), Accent Dot, Reasoner Favicon SVG, Stylized R Letterform

### Community 22 - "Community 22"
Cohesion: 0.53
Nodes (6): Reasoner Logo SVG, Blue Rounded Square Background, Brand Color #3B82F6, Stylized R Letterform, Reasoner Application Identity, White Circle Dot

### Community 23 - "Community 23"
Cohesion: 0.33
Nodes (6): Next.js Framework, Next.js Logo, Next.js Public Folder, Static Asset, SVG Vector Format, ui-next Frontend Project

### Community 24 - "Community 24"
Cohesion: 0.7
Nodes (3): handleUpgrade(), isLoading(), isValidCheckoutUrl()

### Community 25 - "Community 25"
Cohesion: 0.6
Nodes (3): extractText(), Heading(), slugify()

### Community 26 - "Community 26"
Cohesion: 0.6
Nodes (3): cn(), formatDateGroup(), MemoryStatus()

### Community 27 - "Community 27"
Cohesion: 0.4
Nodes (5): Browser Window UI Element, Next.js Public Assets Directory, ui-next Next.js Frontend, Window Control Buttons, Window SVG Icon

### Community 28 - "Community 28"
Cohesion: 0.67
Nodes (2): buildCsp(), withBundleAnalyzer()

### Community 29 - "Community 29"
Cohesion: 0.67
Nodes (2): AuthProvider(), Providers()

### Community 30 - "Community 30"
Cohesion: 0.83
Nodes (2): handleUpgrade(), isValidCheckoutUrl()

### Community 31 - "Community 31"
Cohesion: 0.67
Nodes (2): formatDurationMs(), formatModelLabel()

### Community 32 - "Community 32"
Cohesion: 0.67
Nodes (2): fetcher(), usePresets()

### Community 33 - "Community 33"
Cohesion: 0.67
Nodes (2): MockIntersectionObserver, MockResizeObserver

### Community 34 - "Community 34"
Cohesion: 0.67
Nodes (3): Browser Tab Icon, Reasoner Brand Identity, ui-next Frontend

### Community 35 - "Community 35"
Cohesion: 0.67
Nodes (4): Reasoner Brand Identity, Favicon 32x32 Image, Next.js Public Directory, ui-next Frontend

### Community 36 - "Community 36"
Cohesion: 0.67
Nodes (1): GlobalError()

### Community 37 - "Community 37"
Cohesion: 0.67
Nodes (1): RootLayout()

### Community 38 - "Community 38"
Cohesion: 0.67
Nodes (1): CookiesPage()

### Community 39 - "Community 39"
Cohesion: 0.67
Nodes (1): Hero()

### Community 40 - "Community 40"
Cohesion: 0.67
Nodes (1): LandingFooter()

### Community 41 - "Community 41"
Cohesion: 0.67
Nodes (1): handler()

### Community 42 - "Community 42"
Cohesion: 0.67
Nodes (1): NebulaBackground()

### Community 43 - "Community 43"
Cohesion: 0.67
Nodes (1): NeuroPanel()

### Community 44 - "Community 44"
Cohesion: 0.67
Nodes (1): SecurityBadge()

### Community 45 - "Community 45"
Cohesion: 0.67
Nodes (1): SiteFooter()

### Community 46 - "Community 46"
Cohesion: 0.67
Nodes (1): onScroll()

### Community 47 - "Community 47"
Cohesion: 0.67
Nodes (1): ThreeBackground()

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (1): Badge()

### Community 50 - "Community 50"
Cohesion: 0.67
Nodes (1): isHexColor()

### Community 51 - "Community 51"
Cohesion: 0.67
Nodes (1): Spinner()

### Community 52 - "Community 52"
Cohesion: 0.67
Nodes (1): Tooltip()

### Community 53 - "Community 53"
Cohesion: 0.67
Nodes (1): CalculationWidget()

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (1): WeatherWidget()

### Community 55 - "Community 55"
Cohesion: 0.67
Nodes (1): useConversationHistory()

### Community 56 - "Community 56"
Cohesion: 0.67
Nodes (1): useKeyboardShortcuts()

### Community 57 - "Community 57"
Cohesion: 0.67
Nodes (1): useScrollAnchor()

### Community 58 - "Community 58"
Cohesion: 0.67
Nodes (1): useServerStatus()

### Community 59 - "Community 59"
Cohesion: 0.67
Nodes (1): useSubscription()

### Community 60 - "Community 60"
Cohesion: 0.67
Nodes (1): useWebSocketPipeline()

### Community 61 - "Community 61"
Cohesion: 0.67
Nodes (1): createSupabaseClient()

### Community 62 - "Community 62"
Cohesion: 0.67
Nodes (1): migrate()

### Community 63 - "Community 63"
Cohesion: 0.67
Nodes (3): SaaS-Ready Architecture, Security in Depth, Self-Healing CI

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (2): smart_compress, Token Optimization

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (2): Neuro Learn (Ingest), Neuro Recall (Bootstrap)

### Community 176 - "Community 176"
Cohesion: 1.0
Nodes (1): SWR Server State

### Community 177 - "Community 177"
Cohesion: 1.0
Nodes (1): Project Guidelines Reference

## Knowledge Gaps
- **45 isolated node(s):** `Next.js Breaking Changes Warning`, `Authentication Flow (Pass-Through Proxy)`, `SWR Server State`, `PhaseDispatcher`, `Event Sourcing` (+40 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 19`** (6 nodes): `UsageBadge.tsx`, `useQuota.ts`, `UsageBadge.tsx`, `useQuota.ts`, `UsageBadge()`, `useQuota()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (4 nodes): `next.config.ts`, `buildCsp()`, `next.config.ts`, `withBundleAnalyzer()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (4 nodes): `providers.tsx`, `AuthProvider()`, `Providers()`, `providers.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (4 nodes): `UpgradeModal.tsx`, `UpgradeModal.tsx`, `handleUpgrade()`, `isValidCheckoutUrl()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (4 nodes): `PhaseCard.tsx`, `formatDurationMs()`, `formatModelLabel()`, `PhaseCard.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (4 nodes): `usePresets.ts`, `usePresets.ts`, `fetcher()`, `usePresets()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (4 nodes): `setup.ts`, `MockIntersectionObserver`, `MockResizeObserver`, `setup.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (3 nodes): `global-error.tsx`, `GlobalError()`, `global-error.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (3 nodes): `layout.tsx`, `RootLayout()`, `layout.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (3 nodes): `page.tsx`, `CookiesPage()`, `page.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (3 nodes): `Hero.tsx`, `Hero()`, `Hero.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (3 nodes): `LandingFooter.tsx`, `LandingFooter()`, `LandingFooter.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (3 nodes): `handler()`, `CommandPalette.tsx`, `CommandPalette.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (3 nodes): `NebulaBackground.tsx`, `NebulaBackground()`, `NebulaBackground.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (3 nodes): `NeuroPanel.tsx`, `NeuroPanel()`, `NeuroPanel.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (3 nodes): `SecurityBadge.tsx`, `SecurityBadge()`, `SecurityBadge.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (3 nodes): `SiteFooter.tsx`, `SiteFooter()`, `SiteFooter.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (3 nodes): `SiteHeader.tsx`, `onScroll()`, `SiteHeader.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (3 nodes): `ThreeBackground.tsx`, `ThreeBackground.tsx`, `ThreeBackground()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (3 nodes): `Badge()`, `Badge.tsx`, `Badge.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (3 nodes): `ProfessionalRenderer.tsx`, `isHexColor()`, `ProfessionalRenderer.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (3 nodes): `Spinner.tsx`, `Spinner()`, `Spinner.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (3 nodes): `Tooltip.tsx`, `Tooltip.tsx`, `Tooltip()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (3 nodes): `CalculationWidget()`, `CalculationWidget.tsx`, `CalculationWidget.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (3 nodes): `WeatherWidget.tsx`, `WeatherWidget.tsx`, `WeatherWidget()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (3 nodes): `useConversationHistory.ts`, `useConversationHistory.ts`, `useConversationHistory()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (3 nodes): `useKeyboardShortcuts.ts`, `useKeyboardShortcuts.ts`, `useKeyboardShortcuts()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (3 nodes): `useScrollAnchor.ts`, `useScrollAnchor.ts`, `useScrollAnchor()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (3 nodes): `useServerStatus.ts`, `useServerStatus.ts`, `useServerStatus()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (3 nodes): `useSubscription.ts`, `useSubscription.ts`, `useSubscription()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (3 nodes): `useWebSocketPipeline.ts`, `useWebSocketPipeline.ts`, `useWebSocketPipeline()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (3 nodes): `supabase.ts`, `supabase.ts`, `createSupabaseClient()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (3 nodes): `migrate()`, `app-store.migrate.test.ts`, `app-store.migrate.test.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (2 nodes): `smart_compress`, `Token Optimization`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (2 nodes): `Neuro Learn (Ingest)`, `Neuro Recall (Bootstrap)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 176`** (1 nodes): `SWR Server State`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 177`** (1 nodes): `Project Guidelines Reference`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `POST()` connect `Community 0` to `Community 3`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `Error()` connect `Community 3` to `Community 0`, `Community 5`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `GET()` connect `Community 0` to `Community 10`, `Community 6`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 13 inferred relationships involving `POST()` (e.g. with `validateUpstreamUrl()` and `getApiBaseUrl()`) actually correct?**
  _`POST()` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `GET()` (e.g. with `proxy()` and `POST()`) actually correct?**
  _`GET()` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `handleSubmit()` (e.g. with `handleContinueGenerating()` and `signInWithEmail()`) actually correct?**
  _`handleSubmit()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `fetchWithCsrf()` (e.g. with `apiFetch()` and `fetchJSON()`) actually correct?**
  _`fetchWithCsrf()` has 10 INFERRED edges - model-reasoned connections that need verification._