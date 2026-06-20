# UX Optimization Report — Reasoner (ARA) v2.2

> Research date: 2026-04-22  
> Scope: `ui-next/` frontend UX  
> Method: Codebase audit + industry best-practice research (Perplexity, Claude, Chainlit, Big-AGI, SillyTavern)

---

## 1. Executive Summary

The Reasoner UI is a solid foundation with good component architecture, streaming support, dual transport (SSE + WebSocket), and a clean sidebar/history system. However, several high-impact UX gaps exist that prevent it from feeling production-grade:

| # | Gap | Impact |
|---|-----|--------|
| 1 | **No cost/token transparency** — users have zero visibility into spend or latency | High |
| 2 | **Error states are generic** — all failures collapse to "Connection error" | High |
| 3 | **No retry/edit affordance** — failed messages cannot be retried in-place | High |
| 4 | **Phase cards lack density** — lots of scrolling to see reasoning steps | Medium |
| 5 | **No drag-and-drop for uploads** — only click-to-attach | Medium |
| 6 | **No command palette / power-user shortcuts** — only basic `?` modal | Medium |
| 7 | **No inline memory indicator** — Neuro recall is invisible to the user | Medium |
| 8 | **Composer lacks estimated cost** — no pre-run preview of tokens/time | Medium |
| 9 | **Dark mode unpolished** — no smooth transition, potential contrast issues | Low |
| 10 | **No "Continue generating"** — truncated responses cannot be extended | Low |

---

## 2. Current UX State (What We Have)

### Strengths
- **Streaming architecture** — SSE + WebSocket dual transport with real-time phase transitions (`app/page.tsx`)
- **Phase timeline** — sticky horizontal nav with active/completed/error states (`PhaseTimeline.tsx`)
- **Typewriter reveal** — word-by-word animation with tab-visibility catch-up (`TypewriterMarkdown.tsx`)
- **History persistence** — IndexedDB-backed conversation history with date grouping (`Sidebar.tsx`)
- **Neuro panel** — 3-tab memory interface (Recall / Browse / Learn) (`NeuroPanel.tsx`)
- **Theme toggle** — dark/light mode via `next-themes` (`ThemeToggle.tsx`)
- **Keyboard shortcuts** — `Enter` send, `Shift+Enter` newline, `Esc` stop, `?` help (`ShortcutModal.tsx`)
- **Image generation** — dedicated mode with progress bar and SVG visuals (`ChatFeed.tsx`)
- **WebSocket status indicator** — header dot showing connection state (`page.tsx` header)
- **Resume pipeline** — Play icon on history items to resume interrupted runs (`Sidebar.tsx`)

### Weaknesses
- **No pre-run estimates** — user hits send blind, with no idea of cost or duration
- **Error recovery is poor** — failed runs show a red banner; user must retype or manually retry
- **Attachment UX is minimal** — no drag-and-drop, no upload progress, no preview modal
- **Phase cards are verbose** — each phase renders full-width with large padding; 8 phases = lots of scrolling
- **No inline citations** — sources (when present) are buried in synthesis text, not clickable/numbered
- **Memory is invisible** — when Neuro recall is used, the user has no idea it happened
- **No cost breakdown** — even after completion, users cannot see tokens per phase or total cost
- **Missing shortcuts** — no `Ctrl+K` command palette, `Ctrl+L` clear, `↑` recall, `Ctrl+B` sidebar toggle
- **No feedback loop** — "This wasn't helpful" thumbs up/down missing entirely

---

## 3. Priority Recommendations

### P0 — High Impact, Do First

#### 3.1 Cost & Token Transparency (Pre-Run + Post-Run)

**Problem:** Users send requests with zero cost visibility. After completion, they cannot see what was spent.

**Solution:**
1. **Pre-run estimate badge** in the composer footer:  
   `~1.2k tokens · ~$0.02 · ~8 seconds` (updated live as user types).
2. **Post-run metadata footer** on each assistant message:  
   `2.4k tokens · $0.04 · 12s · 8 phases · auto-research-budget`
3. **Phase-level cost chips** inside each phase card (collapsible, default hidden):  
   `Phase 3 · Critique · 340 tokens · $0.008 · 2.1s`

**Files to modify:**
- `ui-next/src/components/layout/Composer.tsx` — add estimate footer
- `ui-next/src/components/chat/ChatMessage.tsx` — add post-run metadata
- `ui-next/src/components/phases/PhaseCard.tsx` — add cost chip
- `ui-next/src/lib/api-client.ts` — add `estimateCost(problem, preset)` endpoint call
- `src/reasoner/api/routes/pipelines.py` — return `estimated_tokens` / `estimated_cost` in run response

**Effort:** Medium (requires backend pricing API + frontend badge)

---

#### 3.2 Error Recovery & Retry In-Place

**Problem:** All errors look the same (red banner). User must retype or click New Problem.

**Solution:**
1. **Failure taxonomy** — backend should return typed errors: `rate_limit`, `context_length`, `model_unavailable`, `timeout`, `validation_error`.
2. **In-place retry buttons** on failed assistant messages:
   - `Retry` — resend identical request
   - `Retry with Premium` — switch tier and resend (for budget failures)
   - `Edit & Retry` — open composer pre-filled with original prompt
3. **Graceful degradation** — if a phase fails, show partial results + "Continue with available outputs" instead of total failure.

**Files to modify:**
- `ui-next/src/components/chat/ErrorMessage.tsx` — add retry/edit buttons per error type
- `ui-next/src/app/page.tsx` — `handleRetry(messageId)` handler
- `src/reasoner/api/streaming.py` — emit typed error events, not just generic `error`
- `src/reasoner/api/schemas.py` — add `ErrorType` enum

**Effort:** Medium

---

#### 3.3 Inline Source Citations (Perplexity-Style)

**Problem:** Sources are buried in markdown text. Users cannot verify claims without reading everything.

**Solution:**
1. **Superscript citation numbers** in synthesis text: `The market grew 12%[1] in Q3.`
2. **Sources panel** at the top of each assistant message — horizontal scroll of source tiles with favicon + domain + date.
3. **Hover preview** on citations — shows title, url snippet, and confidence.

**Files to modify:**
- `ui-next/src/components/chat/MarkdownRenderer.tsx` — custom remark plugin for `[n]` citations
- `ui-next/src/components/phases/SynthesisCard.tsx` — add `<SourcesPanel>` component
- `src/reasoner/phases/research.py` / `search_mixin.py` — return structured `citations: [{index, title, url, snippet, date}]`

**Effort:** Medium-High (requires backend to emit structured citations)

---

### P1 — High Impact, Medium Effort

#### 3.4 Compact Phase Cards with Progressive Disclosure

**Problem:** 8 phases = 8 full-width cards with large padding. Users scroll excessively.

**Solution:**
1. **Compact mode** — collapsed phases show only: icon + name + duration + status dot. Height ~40px.
2. **Auto-expand first + last + errors** — always show the classification, the synthesis, and any failed phases.
3. **Expand on click** — single click expands any compact phase.
4. **Expand all / Collapse all** — already exists in `PhaseTimeline.tsx`, but should also control card expansion.

**Files to modify:**
- `ui-next/src/components/phases/PhaseCard.tsx` — add `compact` prop with minimal layout
- `ui-next/src/components/chat/ChatFeed.tsx` — default `visiblePhaseCounts` to compact mode
- `ui-next/src/components/layout/PhaseTimeline.tsx` — wire expand/collapse to card state

**Effort:** Low-Medium

---

#### 3.5 Drag-and-Drop File Uploads

**Problem:** Only click-to-attach works. No visual feedback during drag.

**Solution:**
1. **Drag overlay** — when files are dragged over the composer, show a tinted overlay: `Drop files here`.
2. **Upload progress chips** — attachment chips show a thin progress bar during upload.
3. **Paste support** — `Ctrl+V` pastes images from clipboard into attachments.
4. **Preview modal** — click attachment chip to open image preview or PDF text preview.

**Files to modify:**
- `ui-next/src/components/layout/Composer.tsx` — add `dragover`/`drop`/`paste` handlers
- `ui-next/src/components/layout/Composer.tsx` — add progress state to attachment chips
- `ui-next/src/components/chat/ChatFeed.tsx` or new `AttachmentPreviewModal.tsx`

**Effort:** Medium

---

#### 3.6 Inline Memory Indicator

**Problem:** Neuro recall happens silently. Users don't know their past conversations influenced the result.

**Solution:**
1. **Memory badge** on assistant messages that used recall: `Uses 3 memories` with hover showing titles/snippets.
2. **Recall preview** in composer — before sending, if memories will be used, show a subtle line: `Recalling 2 past discussions...`
3. **NeuroPanel highlight** — recalled memories are temporarily highlighted in the Browse tab.

**Files to modify:**
- `ui-next/src/components/chat/ChatMessage.tsx` — add `<MemoryBadge count={3} />`
- `ui-next/src/components/layout/Composer.tsx` — add recall preview line above textarea
- `ui-next/src/components/layout/NeuroPanel.tsx` — highlight recalled entries
- `src/reasoner/api/streaming.py` — emit `recall_used` event with memory IDs/count

**Effort:** Medium

---

### P2 — Medium Impact, Low-Medium Effort

#### 3.7 Command Palette (`Ctrl+K`)

**Problem:** Power users cannot quickly switch presets, search history, or toggle settings without mouse.

**Solution:**
1. **Cmd+K modal** — fuzzy-search commands:
   - `New problem`, `Clear composer`, `Toggle theme`, `Toggle sidebar`
   - `Switch to Premium`, `Open Neuro panel`, `Search history...`
   - `Copy last response`, `Export conversation`
2. **Recent commands** — show last 3 used at top.

**Files to modify:**
- `ui-next/src/components/layout/CommandPalette.tsx` (new)
- `ui-next/src/app/page.tsx` — add global `keydown` listener for `Ctrl+K`
- `ui-next/src/stores/app-store.ts` — add `recentCommands` list

**Effort:** Medium

---

#### 3.8 Keyboard Shortcut Polish

**Problem:** Several standard AI-chat shortcuts are missing.

**Solution:**

| Shortcut | Action | Status |
|----------|--------|--------|
| `Enter` | Send | ✅ |
| `Shift+Enter` | Newline | ✅ |
| `Esc` | Stop | ✅ |
| `?` | Shortcuts modal | ✅ |
| `Ctrl+K` | Command palette | ❌ |
| `Ctrl+L` | Clear composer | ❌ |
| `↑` (empty composer) | Recall last prompt | ❌ |
| `Ctrl+B` | Toggle sidebar | ❌ |
| `Ctrl+Shift+C` | Copy last response | ❌ |
| `/` | Focus composer | ❌ |

**Files to modify:**
- `ui-next/src/hooks/useKeyboardShortcuts.ts` — add missing shortcuts
- `ui-next/src/components/layout/ShortcutModal.tsx` — update reference table

**Effort:** Low

---

#### 3.9 Feedback Loop (Thumbs Up/Down)

**Problem:** No way for users to flag bad outputs. No signal for improvement.

**Solution:**
1. **Thumbs up/down** on each completed assistant message (bottom-right corner).
2. **Follow-up modal** on thumbs down — quick options: `Incorrect`, `Outdated`, `Off-topic`, `Too verbose`, `Unsafe`.
3. **Send feedback** to backend for analytics / fine-tuning.

**Files to modify:**
- `ui-next/src/components/chat/ChatMessage.tsx` — add `<FeedbackButtons>`
- `ui-next/src/components/chat/FeedbackModal.tsx` (new)
- `src/reasoner/api/routes/feedback.py` (new) — POST `/feedback` endpoint

**Effort:** Low-Medium

---

#### 3.10 "Continue Generating" for Truncated Responses

**Problem:** If a response is cut off (token limit), user must re-prompt with "continue".

**Solution:**
1. **Continue button** at bottom of truncated assistant message: `Continue generating...`
2. Backend appends to existing response rather than starting over.

**Files to modify:**
- `ui-next/src/components/chat/ChatMessage.tsx` — add continue button if `truncated: true`
- `src/reasoner/api/routes/pipelines.py` — add `continue_run` endpoint or flag
- `src/reasoner/pipeline.py` — support continuation with prior context

**Effort:** Medium

---

### P3 — Polish & Nice-to-Have

#### 3.11 Dark Mode Transitions & Contrast Audit

**Problem:** Theme switch is instant (no animation). Potential WCAG contrast issues.

**Solution:**
1. **Smooth transition** — add `transition-colors duration-200` to root element.
2. **Audit contrast** — run WebAIM Contrast Checker on `--text` vs `--surface` in both themes.
3. **Avoid pure black** — ensure dark mode uses `#121212` or `#1E1E1E`, not `#000000`.

**Files to modify:**
- `ui-next/src/app/globals.css` — add transition to `:root` and body
- `ui-next/src/app/layout.tsx` — ensure `suppressHydrationWarning` stays

**Effort:** Low

---

#### 3.12 Pre-Run Cost Estimate in Tier Toggle

**Problem:** Tier toggle (Budget/Premium) has no context for what it costs.

**Solution:**
1. **Tooltip on tier toggle** showing estimated cost difference:  
   `Budget: ~$0.02 (faster, lighter models)`  
   `Premium: ~$0.12 (slower, best models)`
2. **In-context upgrade nudge** — if a budget run completes with low confidence, show:  
   `Low confidence result. Retry with Premium?` (one-click)

**Files to modify:**
- `ui-next/src/components/layout/Composer.tsx` — enhance `TierToggle` tooltip
- `ui-next/src/components/chat/ChatMessage.tsx` — add upgrade nudge on low-confidence results

**Effort:** Low

---

## 4. Implementation Roadmap

### Sprint 1 (Week 1) — P0 Foundations
- [ ] 4.1 Backend: Add `estimated_tokens` / `estimated_cost` to run response
- [ ] 4.2 Backend: Emit typed error events (`rate_limit`, `timeout`, etc.)
- [ ] 4.3 Frontend: Pre-run estimate badge in Composer footer
- [ ] 4.4 Frontend: Post-run metadata footer on assistant messages
- [ ] 4.5 Frontend: ErrorMessage with retry/edit buttons

### Sprint 2 (Week 2) — P1 Density & Sources
- [ ] 4.6 Frontend: Compact phase cards with progressive disclosure
- [ ] 4.7 Frontend: Sources panel in SynthesisCard
- [ ] 4.8 Frontend: Drag-and-drop file uploads
- [ ] 4.9 Frontend: Inline memory badge
- [ ] 4.10 Backend: Structured citations in synthesis response

### Sprint 3 (Week 3) — P2 Power-User Features
- [ ] 4.11 Frontend: Command palette (`Ctrl+K`)
- [ ] 4.12 Frontend: Missing keyboard shortcuts
- [ ] 4.13 Frontend: Feedback loop (thumbs up/down)
- [ ] 4.14 Frontend: Continue generating button
- [ ] 4.15 Backend: Feedback endpoint

### Sprint 4 (Week 4) — P3 Polish
- [ ] 4.16 Frontend: Dark mode transition animation
- [ ] 4.17 Frontend: Tier toggle cost tooltip
- [ ] 4.18 Accessibility: Full keyboard nav audit
- [ ] 4.19 Performance: Virtualize long conversation lists

---

## 5. Quick Wins (Can Do Today)

These require minimal code and high UX impact:

1. **Add `Ctrl+L` to clear composer** — ~5 lines in `useKeyboardShortcuts.ts`
2. **Add `↑` arrow recall** — ~10 lines, store last user prompt in `app-store.ts`
3. **Show phase duration in PhaseTimeline** — already tracked, just render it
4. **Add `title` tooltips to all buttons** — many already have them, audit and fill gaps
5. **Smooth theme transition** — 1 CSS line: `transition: background-color 0.2s, color 0.2s`
6. **Pre-fill composer on "Edit & Retry"** — reuse existing `setComposerText`

---

## 6. Appendix: Relevant Files

| File | Current UX Responsibility |
|------|--------------------------|
| `ui-next/src/app/page.tsx` | Root orchestrator, message reducer, event routing |
| `ui-next/src/components/layout/Composer.tsx` | Text input, attachments, tier/image toggles |
| `ui-next/src/components/layout/Sidebar.tsx` | History, Neuro panel toggle, resume/delete |
| `ui-next/src/components/layout/PhaseTimeline.tsx` | Sticky phase nav with status dots |
| `ui-next/src/components/layout/NeuroPanel.tsx` | Recall, Browse, Learn tabs |
| `ui-next/src/components/chat/ChatFeed.tsx` | Message list, streaming states, widgets |
| `ui-next/src/components/chat/ChatMessage.tsx` | Message layout wrapper |
| `ui-next/src/components/phases/PhaseCard.tsx` | Generic phase rendering |
| `ui-next/src/components/phases/SynthesisCard.tsx` | Synthesis with actions/sources |
| `ui-next/src/components/chat/ErrorMessage.tsx` | Error/warning banners |
| `ui-next/src/stores/app-store.ts` | Zustand state + persistence |
| `ui-next/src/hooks/useKeyboardShortcuts.ts` | Global keyboard handlers |
| `src/reasoner/api/streaming.py` | SSE event emitter |
| `src/reasoner/api/routes/pipelines.py` | Run/followup endpoints |
| `src/reasoner/pricing.py` | Cost estimation engine |
