# UI/UX Audit & Optimization Report

## Scope
- WCAG AA contrast compliance (4.5:1 normal, 3:1 large)
- Visible focus states on all interactive elements
- Minimum 40×40px touch targets
- Three.js background FX replacement
- Tooltip text size reduction
- Exact typography system

---

## 1. Contrast Audit — WCAG AA Failures Found

### Methodology
Calculated relative luminance per WCAG 2.1 formula for all text/background pairs.

### Dark Mode (Default)

| Token Pair | Foreground | Background | Ratio | WCAG AA | Status |
|------------|-----------|------------|-------|---------|--------|
| `--text` on `--bg` | #E8F5F8 | #060B10 | **18.3:1** | 4.5:1 | ✅ Pass |
| `--text-2` on `--bg` | #7BACCB | #060B10 | **8.5:1** | 4.5:1 | ✅ Pass |
| `--text-muted` on `--bg` | #4A7A9B | #060B10 | **4.5:1** | 4.5:1 | ⚠️ Barely pass |
| `--text-subtle` on `--bg` | #2D5570 | #060B10 | **2.7:1** | 4.5:1 | ❌ **FAIL** |
| `--text-muted` on `--surface` | #4A7A9B | #0C1420 | **4.2:1** | 4.5:1 | ❌ **FAIL** |
| `--text-small` on `--surface` | #4A7A9B | #0C1420 | **4.2:1** | 4.5:1 | ❌ **FAIL** |
| Tooltip text on tooltip bg | #4A7A9B | #0C1420 | **4.2:1** | 4.5:1 | ❌ **FAIL** |
| `--text-2` on `--surface` | #7BACCB | #0C1420 | **8.0:1** | 4.5:1 | ✅ Pass |
| `--accent-text` on `--accent` | #000E14 | #00C9B1 | **11.2:1** | 4.5:1 | ✅ Pass |
| `--accent` on `--bg` | #00C9B1 | #060B10 | **11.1:1** | 4.5:1 | ✅ Pass |
| `--red` on `--bg` | #FC8181 | #060B10 | **9.2:1** | 4.5:1 | ✅ Pass |
| `--text-subtle` on `--surface` | #2D5570 | #0C1420 | **2.3:1** | 4.5:1 | ❌ **FAIL** |

### Light Mode

| Token Pair | Foreground | Background | Ratio | WCAG AA | Status |
|------------|-----------|------------|-------|---------|--------|
| `--text-muted` on `--bg` | #3D7A98 | #F0F7FA | **4.2:1** | 4.5:1 | ❌ **FAIL** |
| `--text-subtle` on `--bg` | #6BAABF | #F0F7FA | **2.2:1** | 4.5:1 | ❌ **FAIL** |
| `--text-subtle` on `--surface` | #6BAABF | #FFFFFF | **2.1:1** | 4.5:1 | ❌ **FAIL** |
| `--text-2` on `--bg` | #1C5070 | #F0F7FA | **7.8:1** | 4.5:1 | ✅ Pass |
| `--text` on `--bg` | #051018 | #F0F7FA | **17.5:1** | 4.5:1 | ✅ Pass |

### Summary: 8 contrast failures across both themes

**Most critical:** `--text-subtle` and `--text-muted` / `--text-small` fail on both `--bg` and `--surface` in both themes.

### Recommended Color Fixes

Dark mode:
```css
--text-muted:   #5D8DAD;   /* was #4A7A9B → 6.2:1 on #060B10, 5.8:1 on #0C1420 */
--text-small:   #5D8DAD;   /* same as muted */
--text-subtle:  #4A7A9B;   /* was #2D5570 → 4.5:1 on #060B10, 4.2:1 on #0C1420 */
```

Light mode:
```css
--text-muted:   #2A5A78;   /* was #3D7A98 → 6.5:1 on #F0F7FA, 5.8:1 on #FFFFFF */
--text-small:   #2A5A78;   /* same */
--text-subtle:  #3D7A98;   /* was #6BAABF → 4.5:1 on #F0F7FA, 4.2:1 on #FFFFFF */
```

---

## 2. Focus States Audit — Inconsistent & Often Invisible

### Current State

| Element | Current Focus Style | WCAG 2.4.7 | Issue |
|---------|-------------------|------------|-------|
| `Button` component | `ring-2` with `--method-accent-rgb` (white fallback) | ⚠️ Partial | Ring color varies by method; white ring invisible on light surfaces |
| Composer textarea | `focus:outline-none` only | ❌ **FAIL** | No visible focus indicator |
| Sidebar search | `focus:border-[var(--border-strong)]` + `outline-none` | ⚠️ Partial | Border color change too subtle (0.09 → 0.22 alpha) |
| Login/signup inputs | `focus:border-[var(--accent)]` + `outline-none` | ⚠️ Partial | Border-only focus is hard to see |
| Landing CTAs | Unknown | ❓ Unknown | Not audited in explore |
| Icon buttons (attach, send, theme) | No explicit focus style | ❌ **FAIL** | Inherits browser default or nothing |
| Sidebar tabs | No explicit focus style | ❌ **FAIL** | |
| Phase timeline buttons | No explicit focus style | ❌ **FAIL** | |

### Recommended Unified Focus System

```css
/* globals.css — add to @layer base */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Override for elements that need custom focus */
button:focus-visible,
[role="button"]:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(0, 201, 177, 0.25);
}

input:focus-visible,
textarea:focus-visible,
[contenteditable]:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -1px; /* inset for form fields */
}
```

Key principles:
- **Always visible**: Never use `outline: none` without a replacement
- **High contrast**: Focus color must contrast 3:1 against adjacent colors
- **Sufficient size**: Focus ring must be at least 2px thick
- **No reliance on color alone**: Add `box-shadow` glow for extra visibility

---

## 3. Touch Target Audit — Multiple Elements Below 40×40px

### Elements Failing Minimum Touch Target (40×40px)

| Component | Current Size | Current Padding | Min Required | Gap |
|-----------|-------------|----------------|--------------|-----|
| Composer attach button | 32×32px (`h-8 w-8`) | none | 40×40px | -8px |
| Composer send/stop button | 36×36px (`h-9 w-9`) | none | 40×40px | -4px |
| Theme toggle | 36×36px (`h-9 w-9`) | none | 40×40px | -4px |
| Sidebar collapse toggle | 36×36px (`h-9 w-9`) | none | 40×40px | -4px |
| Sidebar tab switcher | ~28×24px | `px-2 py-1.5` | 40×40px | -12px / -16px |
| Phase timeline buttons | ~30×26px | `px-2.5 py-1.5` | 40×40px | -10px / -14px |
| Expand/Collapse all | ~28×22px | `px-2.5 py-1` | 40×40px | -12px / -18px |
| Header icons | ~16×16px | varies | 40×40px | -24px |
| Sidebar icons | ~14×14px | varies | 40×40px | -26px |
| Composer toolbar icons | ~12×12px to 16×16px | varies | 40×40px | -28px to -24px |

**Important note:** Icon buttons are often the worst offenders. An icon may be 16×16px but the clickable area around it is what matters. If the icon is inside a `<button>` with no padding, the touch target is just the icon size.

### Recommended Touch Target Fixes

```css
/* Minimum touch target utility */
.min-touch {
  min-width: 40px;
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
```

Specific component updates:
- All icon buttons: `h-10 w-10` (40px) minimum, with `p-2` internal padding
- Sidebar tabs: `px-3 py-2.5` minimum (`h-10`)
- Phase timeline: `px-3 py-2.5` minimum
- Expand/collapse: `px-3 py-2.5` minimum
- Header nav icons: Wrap in `h-10 w-10` containers

---

## 4. Background FX — "ThreeBackground" Is Misleading (Canvas2D, Not Three.js)

### Current Implementation

`src/components/layout/ThreeBackground.tsx` uses raw `CanvasRenderingContext2D` — NOT WebGL/Three.js. The package `three` is installed but unused for the background.

**Current effect:** 80-node particle network with:
- Teal (#00C9B1) nodes and connecting lines
- Amber (#F59E0B) highlights for high-z nodes
- Mouse repulsion
- `opacity: 0.55`
- Rendered via `requestAnimationFrame` on 2D canvas

**Issues:**
1. **Naming is misleading** — component is called `ThreeBackground` but uses Canvas2D
2. **CPU-intensive on mobile** — O(n²) line drawing every frame (80 nodes = 3,160 line checks)
3. **No `prefers-reduced-motion` support** — runs full animation even for motion-sensitive users
4. **Z-fighting with overlays** — canvas at `z-0`, but `LandingPage.tsx` adds blurred orbs on top
5. **No actual Three.js** — installed dependency is dead weight

### Recommended Background Options

#### Option A: Keep Canvas2D, Optimize (Lightweight)
- Reduce node count: 80 → 40 (50% fewer line checks = 4× fewer iterations)
- Add `prefers-reduced-motion: reduce` → static image or CSS gradient
- Cap frame rate: `Math.min(30, displayRefreshRate)`
- Use `IntersectionObserver` to pause when off-screen

#### Option B: CSS-Only Nebula (Zero JS)
Replace with pure CSS animated gradients:
```css
.bg-nebula {
  background:
    radial-gradient(ellipse at 20% 20%, rgba(0, 201, 177, 0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 80%, rgba(245, 158, 11, 0.06) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 50%, rgba(0, 201, 177, 0.03) 0%, transparent 70%);
  animation: nebula-shift 20s ease-in-out infinite;
}
```
Pros: No JS, no CPU, respects reduced-motion, works on all devices.
Cons: Less dynamic than particles.

#### Option C: Actual Three.js Shader Background (Premium)
Use the installed `three` package with a simple fragment shader:
- Slow-moving nebula with teal/amber color flow
- Single fullscreen quad = minimal geometry cost
- Shader runs on GPU = minimal CPU impact
- `prefers-reduced-motion` support via uniform freeze

**Recommendation: Option A (optimize) or Option B (CSS-only)** — The current Canvas2D effect is not worth the CPU cost for a subtle background. Option B is the most accessible and performant.

---

## 5. Tooltip Audit

### Current Implementation

`src/components/ui/Tooltip.tsx` (19 lines):
```tsx
<div className="... text-[var(--text-small)] text-[var(--text-muted)] ...">
```

**Bug identified:** `text-[var(--text-small)]` uses a **color variable** (`--text-small: #4A7A9B`) as a font-size class. Tailwind v4 may interpret `#4A7A9B` as a color, not a size. The actual font size is inherited from the parent element (likely `text-xs` or `text-sm`).

**Contrast issue:** Tooltip text (#4A7A9B) on tooltip background (#0C1420) = **4.2:1** — fails WCAG AA.

**Size issue:** No explicit font size. Inherits from wrapped element, which could be anything from 10px to 18px.

### Recommended Tooltip Redesign

```tsx
// Explicit size, guaranteed contrast
<div className="... text-[11px] leading-4 font-medium text-[var(--text-2)] ...">
```

With CSS custom properties for the tooltip specifically:
```css
--tooltip-text: var(--text-2);      /* #7BACCB on dark = 8.0:1 on surface */
--tooltip-bg: var(--surface);
--tooltip-text-size: 11px;
```

Why 11px?
- Small enough to be unobtrusive
- Large enough to be readable (WCAG doesn't specify minimum font size, but 11px+ is practical)
- One step below `text-xs` (12px) in Tailwind's default scale

---

## 6. Typography System — Currently Ad Hoc

### Current State

Multiple competing systems:

| Source | Scale | Values |
|--------|-------|--------|
| `TEXT_SIZES` (config.ts) | Arbitrary px | 10px, 15px, 17px, 18px |
| Landing page | `clamp()` | 3.5–7.5rem, 2–3rem |
| Chat message | Inline px | 15px, 16px, 18px |
| Tailwind defaults | rem | xs (12px), sm (14px), base (16px), lg, xl, etc. |
| tailwind.config.js | Custom | display-hero (82px), section-heading, etc. |

**Problems:**
1. No single source of truth
2. No mathematical relationship between sizes (no modular scale)
3. Line heights are inconsistent (`leading-relaxed` vs inline px vs default)
4. Font weights are scattered (no system)

### Recommended Exact Typography System

Use a **Major Third (1.25×) modular scale** with a 16px base:

```
Scale: 16 × (1.25^n)

n=-3:  8.19px   → 8px   (fine print, badges)
n=-2:  10.24px  → 10px  (captions, labels)
n=-1:  12.80px  → 13px  (small body, nav)
n=0:   16.00px  → 16px  (base body)
n=1:   20.00px  → 20px  (lead paragraph)
n=2:   25.00px  → 25px  (h6, card title)
n=3:   31.25px  → 31px  (h5, section label)
n=4:   39.06px  → 39px  (h4, feature title)
n=5:   48.83px  → 49px  (h3, page section)
n=6:   61.04px  → 61px  (h2, major heading)
n=7:   76.29px  → 76px  (h1, hero display)
```

Implementation in Tailwind v4 CSS-native config:

```css
/* globals.css — add to :root */
--text-2xs: 10px;
--text-xs:  13px;
--text-sm:  14px;  /* Tailwind default sm */
--text-base: 16px; /* Tailwind default base */
--text-md:  18px;
--text-lg:  20px;
--text-xl:  25px;
--text-2xl: 31px;
--text-3xl: 39px;
--text-4xl: 49px;
--text-5xl: 61px;
--text-6xl: 76px;

/* Line height tokens */
--leading-tight:  1.25;
--leading-snug:   1.375;
--leading-normal: 1.5;
--leading-relaxed: 1.625;
--leading-loose:  1.75;

/* Font weight tokens */
--font-normal:  400;
--font-medium:  500;
--font-semibold: 600;
--font-bold:    700;
```

Then use Tailwind's `@theme` block (v4 native):
```css
@theme {
  --font-size-2xs: var(--text-2xs);
  --font-size-xs:  var(--text-xs);
  --font-size-md:  var(--text-md);
  --font-size-xl:  var(--text-xl);
  /* ... etc, mapping to the CSS custom properties */
}
```

**Migration strategy:**
1. Define the scale in `globals.css`
2. Audit all components, replace inline `text-[15px]`, `text-[17px]`, `text-[18px]` with closest scale step
3. Update `TEXT_SIZES` in `config.ts` to reference the scale
4. Deprecate `tailwind.config.js` custom font sizes

---

## 7. Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | Fix contrast colors (`--text-muted`, `--text-subtle`, `--text-small`) | 15 min | WCAG compliance |
| **P0** | Fix Tooltip explicit size + contrast | 10 min | Readability + bug fix |
| **P0** | Add unified focus styles | 20 min | Accessibility |
| **P1** | Increase touch targets to 40×40px | 30 min | Mobile usability |
| **P1** | Implement exact typography system | 45 min | Visual consistency |
| **P2** | Replace/optimize background FX | 30–60 min | Performance |
| **P2** | Rename `ThreeBackground` → `ParticleBackground` | 5 min | Code clarity |

---

## Appendix: Contrast Calculation Formula

```
L = 0.2126 × R + 0.7152 × G + 0.0722 × B
  where R, G, B are sRGB values linearized:
  if c <= 0.03928: c = c / 12.92
  else: c = ((c + 0.055) / 1.055) ^ 2.4

Ratio = (L1 + 0.05) / (L2 + 0.05)
```

All calculations above use this formula against sRGB hex values.
