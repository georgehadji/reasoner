# UX Optimization Research — Reasoner Frontend

> **Scope:** `ui-next/src/` | **Date:** 2026-04-30 | **Analyst:** Kimi Code
> **Methodology:** Code audit + heuristic evaluation against WCAG 2.2, Refactoring UI principles, and modern AI-product UX patterns.

---

## Executive Summary

The Reasoner frontend has a **solid architectural foundation** (design tokens, feature flags, proper state management, memoization) but suffers from **three high-impact UX categories** that degrade perceived performance and usability:

1. **Rendering Performance** — The chat page (1,136 lines) is a rendering bottleneck. Streaming causes cascading re-renders across the entire message tree.
2. **Visual Feedback** — Error states, loading states, and completion signals are visually underpowered. Users don't get enough confidence that the system is working.
3. **Reasoning Transparency** — The phase timeline is good, but intermediate reasoning steps are often collapsed or overwhelming. Users can't easily follow the "why" behind answers.

**Estimated impact if all P0/P1 items are implemented:**
- 40-60% reduction in frame drops during streaming
- 25% faster perceived response time (skeletons + progress clarity)
- Significantly improved mobile experience (touch targets, scroll, layout)

---

## 1. Performance & Rendering (P0 — Critical)

### 1.1 Chat Page Monolith — Component Splitting
**File:** `app/chat/page.tsx` (1,136 lines)

**Problem:** The chat page mixes state management, event handling, rendering logic, and side effects in a single component. Every `dispatchMessages` or `setState` triggers a re-render of the entire page — including Sidebar, Composer, PhaseTimeline, and all ChatFeed messages.

**Evidence:**
```tsx
// 153 useState/setState calls + reducer dispatch in one component
// Sidebar receives `messages` prop and re-renders on every streaming chunk
// PhaseTimeline re-renders on every phase duration update
```

**Recommended Fix:**
| Extract To | Lines | Responsibility |
|---|---|---|
| `ChatContainer.tsx` | ~200 | Layout shell (header, sidebar slot, composer slot) |
| `useChatEngine.ts` | ~350 | All SSE event handling, reducer logic, refs |
| `ChatMessageList.tsx` | ~150 | Virtualized or memoized message list |
| `RunOrchestrator.ts` | ~200 | Start/stop/resume/followup API coordination |

**Quick win (no refactor):** Wrap `Sidebar`, `Composer`, and `PhaseTimeline` in `React.memo()` with custom comparison. The sidebar only needs `history` and `conversationId`, not `messages`.

---

### 1.2 Streaming Markdown Re-renders
**File:** `components/chat/MarkdownRenderer.tsx`

**Problem:** `MarkdownRenderer` is memoized, but the `children` string changes on every SSE `text_chunk`. This causes `ReactMarkdown` to re-parse the entire AST on every chunk (up to 30-60× per second during fast streaming).

**Evidence:**
```tsx
export const MarkdownRenderer = memo(MarkdownRendererComponent);
// Still re-renders because `children` is a new string every time
```

**Recommended Fix:** Use `StreamingMarkdown` for streaming content (which you already have) but ensure it only renders the **delta**, not the full content. For final content, use `MarkdownRenderer`.

```tsx
// In ChatFeed: don't pass `streamingContent` through MarkdownRenderer
// Instead, append raw text with a simple <span> during streaming,
// then switch to MarkdownRenderer when isStreaming=false
```

---

### 1.3 PhaseTimeline Re-computation
**File:** `components/layout/PhaseTimeline.tsx`

**Problem:** `METHOD_PHASES[normalized]` lookup and phase status calculations happen on every render. With 10+ phases and frequent state updates, this adds up.

**Quick Fix:**
```tsx
// Memoize the phases array and status map
const phaseList = useMemo(() => METHOD_PHASES[normalized] || METHOD_PHASES['multi-perspective'], [normalized]);
const statusMap = useMemo(() => {
  const map = new Map<number, 'pending' | 'active' | 'completed' | 'error'>();
  phaseList.forEach(p => {
    if (errorPhases.includes(p.id)) map.set(p.id, 'error');
    else if (currentPhase === p.id) map.set(p.id, 'active');
    else if (completedPhases.includes(p.id)) map.set(p.id, 'completed');
    else map.set(p.id, 'pending');
  });
  return map;
}, [phaseList, currentPhase, completedPhases, errorPhases]);
```

---

### 1.4 Sidebar List Re-computation
**File:** `components/layout/Sidebar.tsx`

**Current state:** Already using `useMemo` for filtering and grouping — good. But `grouped` is recalculated whenever `conversations` changes (which happens after every run when history refreshes).

**Optimization:** Use `useCallback` for `formatDateGroup` and consider virtualizing the conversation list if users accumulate >100 conversations.

---

## 2. Visual Design & Hierarchy (P1 — High)

### 2.1 Accent Color is Visually Inert
**File:** `app/globals.css`

**Problem:** The current accent is `#707070` (medium gray). This fails two Refactoring UI principles:
- **Hierarchy:** The primary action button doesn't stand out from the background
- **Affordance:** Users can't instantly identify what's clickable

**Current:**
```css
--accent:       #707070;
--accent-hover: #505050;
```

**Recommended:** Restore a desaturated but identifiable brand color. For a "security/trust" product, a muted steel-blue works better than pure gray:

```css
/* Dark mode */
--accent:       #5B8DB8;  /* Muted steel blue — trustworthy, not flashy */
--accent-hover: #7BA3C8;
--accent-dim:   rgba(91, 141, 184, 0.15);
--accent-glow:  0 0 40px rgba(91, 141, 184, 0.20);

/* Light mode */
--accent:       #2563EB;  /* Classic corporate blue */
--accent-hover: #3B82F6;
```

**Why:** Gray-on-gray creates "muddy" interfaces. Users need *some* color to anchor their attention. The steel-blue maintains the security aesthetic while providing actual hierarchy.

---

### 2.2 Error Color is Invisible
**File:** `app/globals.css`

**Problem:** `--red: #404040` is darker than `--text-muted: #A0A0A0`. Error states look like normal text.

**Fix:**
```css
--red:        #EF4444;  /* Visible but not neon */
--red-bg:     rgba(239, 68, 68, 0.10);
--red-border: rgba(239, 68, 68, 0.25);
```

---

### 2.3 Legacy Color Tokens in ChatFeed
**File:** `components/chat/ChatFeed.tsx`

**Problem:** Hardcoded references to old design system colors:
```tsx
bg-mds-color-dark-charcoal
bg-mds-color-cool-gray/[0.4]
text-mds-color-mid-gray
```

These create visual inconsistency and break if the old token definitions are ever removed.

**Fix:** Map these to CSS variables:
```tsx
// Instead of bg-mds-color-dark-charcoal
className="bg-[var(--surface)]"

// Instead of text-mds-color-mid-gray  
className="text-[var(--text-muted)]"
```

---

### 2.4 Phase Card Borders in Light Mode
**File:** `components/phases/PhaseRenderer.tsx`

**Problem:** Multiple uses of `border-white/10` and `bg-white/5` which are invisible in light mode:
```tsx
<div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
```

**Fix:** Replace with semantic tokens:
```tsx
<div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
```

---

### 2.5 Heading Text Shadows Hurt Readability
**File:** `app/globals.css`

```css
h1, h2, h3 {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}
```

**Problem:** Text shadows on body text reduce perceived sharpness, especially on high-DPI screens. In light mode, dark shadows on dark text create halos.

**Fix:** Remove or scope to decorative hero headings only:
```css
/* Remove from global h1-h3 */
/* Apply only to landing hero */
.hero-heading {
  text-shadow: 0 0 40px rgba(224,224,224,0.35), 0 0 100px rgba(160,160,160,0.18);
}
```

---

## 3. Interaction & Feedback (P1 — High)

### 3.1 No Skeleton Loading State
**Current behavior:** Empty composer area shows "Brainstorm ideas" heading, then nothing happens until the first SSE event.

**Problem:** On slow networks or complex problems, there's 2-8 seconds of dead air before any visual feedback. Users often think the app is broken.

**Recommended:** Add a "Reasoning Pipeline" skeleton that mirrors the phase timeline:

```tsx
// Shown immediately after submit, before first SSE event
<PipelineSkeleton>
  <PhaseSkeleton name="Classify" delay={0} />
  <PhaseSkeleton name="Decompose" delay={150} />
  <PhaseSkeleton name="Analyze" delay={300} />
  {/* ... etc */}
</PipelineSkeleton>
```

Each phase skeleton pulses in sequence, giving users an immediate sense of progress and expected wait time.

---

### 3.2 File Validation Uses `alert()`
**File:** `components/layout/Composer.tsx`

```tsx
if (attachments.length >= LIMITS.maxAttachments) { alert('Maximum 5 files allowed.'); break; }
```

**Problem:** `alert()` blocks the main thread, feels jarring, and breaks the visual flow.

**Fix:** Inline toast or composer-level inline error:
```tsx
{fileError && (
  <div className="rounded-lg border border-[var(--red-border)] bg-[var(--red-bg)] px-3 py-2 text-sm text-[var(--red)]">
    {fileError}
  </div>
)}
```

---

### 3.3 PhaseTimeline Horizontal Scroll is Hidden
**File:** `components/layout/PhaseTimeline.tsx`

**Problem:** On mobile or narrow viewports, phases overflow horizontally. The `overflow-x-auto` scrollbar is hidden by default on most systems, giving no indication that more phases exist.

**Fix:** Add a subtle fade gradient on the right edge when overflow is present:
```tsx
<div className="relative">
  <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-thin pb-px">
    {/* phases */}
  </div>
  {/* Fade indicator */}
  <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 
    bg-gradient-to-l from-[var(--bg)] to-transparent" />
</div>
```

Also consider a "current phase" sticky pill on mobile instead of the full timeline.

---

### 3.4 No Completion Signal
**Problem:** When a long reasoning pipeline finishes, there's no auditory or visual "done" signal. Users may not notice completion if they're tabbed away.

**Recommended:**
- A subtle completion animation on the final synthesis card (checkmark morph)
- Optional: browser notification for runs >30s (`new Notification()`)
- Auto-scroll to the synthesis section when complete

---

### 3.5 Missing "Copy" on Streaming Content
**File:** `components/chat/ChatFeed.tsx`

**Problem:** The `MessageActions` bar (copy, feedback, tokens) only appears on completed messages. Users can't copy partial output during streaming.

**Fix:** Show a disabled or simplified actions bar during streaming:
```tsx
{isStreaming && (
  <div className="opacity-50">
    <CopyButton disabled text={content + streamingContent} />
  </div>
)}
```

---

## 4. Reasoning Transparency (P1 — High)

### 4.1 Method Selection is Opaque
**Problem:** The HyperGate auto-selects a reasoning method, but users don't know why `delphi` was chosen over `debate`. The `autoSelectedMethod` state is displayed nowhere in the UI.

**Recommended:** Show a small "Reasoning method: Delphi (consensus-seeking)" badge above the phase timeline, with a tooltip explaining why:
```tsx
<Tooltip text="Delphi was chosen because your question involves expert opinion aggregation">
  <span className="text-xs text-[var(--text-muted)]">
    Method: {methodName}
  </span>
</Tooltip>
```

---

### 4.2 Quality Scores are Invisible
**File:** `components/phases/PhaseRenderer.tsx`

**Problem:** `quality` data is extracted but never prominently displayed. Users don't know if a phase passed internal quality gates.

**Recommended:** Add a micro-badge to completed phases:
```tsx
{quality && (
  <span className={cn(
    "text-[10px] font-medium px-1.5 py-0.5 rounded",
    quality.passed ? "bg-green-500/10 text-green-400" : "bg-amber-500/10 text-amber-400"
  )}>
    {quality.passed ? "✓ Pass" : `⚠ ${quality.score.toFixed(0)}%`}
  </span>
)}
```

---

### 4.3 Model Names are Truncated Too Aggressively
**File:** `components/chat/ChatFeed.tsx`

```tsx
{m.split('/').pop() || m}
```

**Problem:** `anthropic/claude-3.5-sonnet` becomes `claude-3.5-sonnet`, which is good. But on narrow screens, even this gets cut off. Users can't see which models are participating.

**Fix:** Show model names in a collapsible "Details" section within each phase card, not just as inline chips.

---

## 5. Accessibility (P1 — High)

### 5.1 Live Region for Chat Feed
**Current:** `aria-live="polite"` is on `PhaseTimeline`, not the chat feed.

**Problem:** Screen reader users don't hear streaming content or phase completions.

**Fix:** Add an ARIA live region to the chat feed:
```tsx
<div aria-live="polite" aria-atomic="false" className="sr-only">
  {currentPhaseName && `Running ${currentPhaseName}`}
  {lastMessageContent}
</div>
```

---

### 5.2 Phase Status Relies on Color Alone
**File:** `components/layout/PhaseTimeline.tsx`

**Problem:** Active phase = green dot, error = red dot, completed = gray dot. No text label for status.

**Fix:** Add `aria-label` to each phase button:
```tsx
aria-label={`${p.name} — ${isActive ? 'In progress' : isError ? 'Error' : isCompleted ? 'Completed' : 'Pending'}`}
```

---

### 5.3 No Skip Link
**Problem:** Keyboard users must tab through the entire sidebar to reach the main chat content.

**Fix:** Add a skip link:
```tsx
<a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-[var(--accent)] focus:text-white">
  Skip to main content
</a>
```

---

### 5.4 prefers-reduced-motion Not Fully Respected
**Current:** `motion-reduce:animate-none` is used in PhaseTimeline but not globally.

**Fix:** Add to globals.css:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  /* Keep opacity transitions for state changes */
  .preserve-transition { transition-duration: 150ms !important; }
}
```

---

## 6. Mobile UX (P2 — Medium)

### 6.1 Composer Keyboard Handling
**File:** `components/layout/Composer.tsx`

**Current:** `min-h-[28px]` on bottom-bar layout, `min-h-[120px]` on centered.

**Problem:** On iOS, the keyboard pushes content up but the composer stays at the bottom (good). However, when attachments are added, the composer grows and can obscure half the screen.

**Fix:** Cap composer max-height and make it scrollable:
```tsx
<textarea
  className="... max-h-[40vh] overflow-y-auto"
/>
```

---

### 6.2 Sidebar Toggle on Mobile
**Current:** Mobile sidebar uses a fixed backdrop + slide. Good pattern.

**Problem:** When sidebar is open, swiping right to go back (iOS gesture) conflicts with sidebar close.

**Fix:** Add `touch-action: pan-y` to the sidebar to prevent horizontal swipe hijacking.

---

### 6.3 Touch Targets
**Current state:** Most buttons are `h-10 w-10` (40px). Close to Apple's 44px minimum.

**Quick fix:** Increase to `h-11 w-11` (44px) for all icon-only buttons:
```tsx
// In Tooltip buttons and action buttons
className="h-11 w-11 ..."
```

---

## 7. Onboarding & Discovery (P2 — Medium)

### 7.1 Example Prompts are Static
**File:** `lib/config.ts`

```tsx
export const EXAMPLE_PROMPTS = [
  'Should I bootstrap or raise VC?',
  'What assumptions am I making about remote work?',
  // ... 9 total
];
```

**Problem:** Same prompts every time. Users quickly learn to ignore them.

**Recommended:** Rotate prompts based on:
- Time of day (morning = productivity, evening = philosophical)
- User's previous conversation topics
- Seasonal/trending topics

Also add a "Surprise me" button that picks a random prompt.

---

### 7.2 No First-Run Guidance
**Problem:** New users land in `/chat` with an empty composer and no idea what Reasoner does differently from ChatGPT.

**Recommended:** A one-time overlay or inline tooltip series:
1. "Reasoner verifies every claim across multiple AI models"
2. "Watch the phase timeline to see how your answer is built"
3. "Try asking a complex question — Reasoner shines on hard problems"

Dismissible and stored in `localStorage`.

---

### 7.3 Method Names are Jargon
**Problem:** Sidebar shows method names like `multi-perspective`, `aufhebung`, `pre-mortem` without explanation.

**Fix:** Add a method glossary tooltip or a small info icon next to method tags:
```tsx
<Tooltip text="Multi-Perspective: Analyzes your problem from 3-5 different expert viewpoints simultaneously">
  <span className="...">multi-perspective</span>
</Tooltip>
```

---

## 8. Information Architecture (P2 — Medium)

### 8.1 Token/Cost Display is Too Subtle
**File:** `components/chat/ChatFeed.tsx`

**Current:** Tokens and cost appear in tiny text below completed messages.

**Problem:** Power users want this data. Casual users don't care. Current placement satisfies neither.

**Recommended:** Collapsible "Details" section on each message:
```tsx
<details className="text-xs text-[var(--text-subtle)]">
  <summary>Details</summary>
  Tokens: {tokens.total} · Cost: ${cost?.toFixed(4)} · Duration: {formatDuration(duration)}
</details>
```

---

### 8.2 Conversation Search Only Searches Problem Text
**File:** `components/layout/Sidebar.tsx`

```tsx
const matchesQuery = !query.trim() || c.problem.toLowerCase().includes(query.toLowerCase());
```

**Problem:** Users can't search for content within responses.

**Fix:** Index response content in IndexedDB and search across both `problem` and `response_content`.

---

### 8.3 No Conversation Folders/Organization
**Problem:** As conversation history grows, the flat chronological list becomes unwieldy.

**Recommended (future):** Auto-tag conversations by topic and allow filtering by:
- Domain (business, science, creative, coding)
- Method used
- Date range
- Has attachments

---

## Priority Action Matrix

| Priority | Item | Effort | Impact | File(s) |
|---|---|---|---|---|
| **P0** | Memoize Sidebar, Composer, PhaseTimeline | 30 min | High | `chat/page.tsx` |
| **P0** | Fix streaming re-render (delta-only) | 2 hrs | Very High | `chat/page.tsx`, `ChatFeed.tsx` |
| **P0** | Restore visible accent color | 15 min | High | `globals.css` |
| **P1** | Fix error color visibility | 5 min | High | `globals.css` |
| **P1** | Replace `alert()` with inline errors | 30 min | Medium | `Composer.tsx` |
| **P1** | Add skeleton loading state | 2 hrs | Very High | New file + `chat/page.tsx` |
| **P1** | Fix legacy color tokens in ChatFeed | 1 hr | Medium | `ChatFeed.tsx` |
| **P1** | Add ARIA live region to chat | 30 min | High | `ChatFeed.tsx` |
| **P1** | Add phase status labels (not just color) | 30 min | High | `PhaseTimeline.tsx` |
| **P1** | Add method explanation badge | 1 hr | Medium | `chat/page.tsx` |
| **P1** | Show quality scores on phases | 1 hr | Medium | `PhaseRenderer.tsx` |
| **P2** | Mobile touch target increase | 15 min | Medium | Multiple |
| **P2** | Skip link for keyboard nav | 15 min | Medium | `layout.tsx` |
| **P2** | prefers-reduced-motion global | 15 min | Medium | `globals.css` |
| **P2** | Rotating example prompts | 30 min | Low | `config.ts` |
| **P2** | First-run onboarding tooltip | 2 hrs | Medium | New file |

---

## Appendix: Design Principle Alignment

### Refactoring UI Principles — Current Grade

| Principle | Grade | Notes |
|---|---|---|
| Visual Hierarchy | B | Good spacing, but gray accent weakens primary actions |
| Typography | A | Consistent scale, good line heights |
| Color | C | Error colors invisible, accent too muted, legacy tokens |
| Spacing | A | Generous padding, good proximity relationships |
| Layout | B | Clean structure, but chat page is overloaded |
| Empty States | B | Sidebar has good empty state; chat empty state is plain |
| Dark Mode | B | Well-implemented, but some hardcoded `border-white/10` |
| Forms | A | Composer is excellent (drag-drop, attachments, shortcuts) |

### WCAG 2.2 Compliance — Quick Check

| Criterion | Status | Fix Needed |
|---|---|---|
| 1.4.3 Contrast (text) | ⚠️ Partial | Error text fails; some subtle text borderline |
| 1.4.11 Contrast (non-text) | ⚠️ Partial | Phase dots need 3:1 against background |
| 2.4.7 Focus Visible | ✅ Pass | Good `focus-visible` implementation |
| 2.5.5 Target Size | ⚠️ Partial | Some buttons are 40px, not 44px |
| 2.2.2 Pause/Stop/Hide | ✅ Pass | Animations are subtle |
| 2.3.3 Animation from Interactions | ⚠️ Partial | No `prefers-reduced-motion` globally |

---

*End of Research Document*
