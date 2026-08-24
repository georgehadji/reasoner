# Context: Chat

## Directory: `ui-next/src/components/chat`

## Description
Interactive chat message components, streaming tokens, and reasoning process indicators.

## Files
- **`ChatErrorBoundary.tsx`**: Code or resource asset facilitating system functionality.
- **`ChatFeed.tsx`**: One transition token for every row that lands in the feed, so a user turn, an error and an assistant turn arrive with the same gesture. `both` holds the from-state through the stagger delay, so
- **`ChatMessage.tsx`**: Code or resource asset facilitating system functionality.
- **`CodeBlock.tsx`**: Heavily-lazy loaded syntax-highlighted code block. This entire file (~400KB with Prism) is split into its own JS chunk and only loaded when a code block appears in markdown.
- **`ErrorMessage.tsx`**: height is the WCAG 2.5.5 touch target — the icons alone are 14px.
- **`ManifestationVisuals.tsx`**: Expanding rings. `delay` drives the animated version; `staticSize` / `staticOpacity` are the frozen concentric snapshot rendered instead when the user has asked for reduced motion.
- **`MarkdownRenderer.patterns.test.ts`**: Find the anchor renderer function
- **`MarkdownRenderer.tsx`**: CodeBlock is in its own JS chunk (~400KB with Prism), loaded on demand
- **`MethodChoicePrompt.tsx`**: Shown when HyperGate's confidence in its top method pick is below HYPERGATE_METHOD_THRESHOLD. Lets the user confirm the suggested method, pick a runner-up, or opt out of being asked again.
- **`PipelineSkeleton.tsx`**: Code or resource asset facilitating system functionality.
- **`StreamingMarkdown.tsx`**: StreamingMarkdown — renders finalized markdown content with an optional cursor. NOTE: Do NOT use this for live SSE streaming. During active streaming, ChatFeed renders raw text directly to avoid re-parsing the full Markdown

## Subfolders
*No subfolders in this directory.*
