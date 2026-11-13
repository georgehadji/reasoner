# Background FX Research

Ideas for ambient visual effects behind the Reasoner chat interface. All recommendations are evaluated against the ElevenLabs-inspired design system (warm, minimal, surfaces that "barely exist").

---

## Approach Overview

| # | Approach | Bundle | Complexity | Perf | Fit |
|---|----------|:------:|:----------:|:----:|:---:|
| 1 | CSS Organic Blobs | 0kb | Trivial | ★★★★★ | ★★★★ |
| 2 | Canvas Particle Mist | 0kb | Low | ★★★★★ | ★★★★★ |
| 3 | Canvas Data Flow | 0kb | Low | ★★★★ | ★★★★ |
| 4 | CSS Film Grain Noise | 0kb | Trivial | ★★★★★ | ★★★★ |
| 5 | @react-three/fiber Particles | ~150kb gzip | Medium | ★★★ | ★★★★★ |
| 6 | @react-three/fiber Wireframe Geometry | ~150kb gzip | Medium | ★★★ | ★★★★ |
| 7 | CSS + Canvas Mesh Gradient | 0kb | Low | ★★★★ | ★★★★★ |
| 8 | GSAP Morphing Shapes | ~30kb gzip | Low | ★★★★★ | ★★★ |

---

## 1. CSS Organic Blobs

**Library:** None (pure CSS)

**Description:** Warm-toned blurred shapes that slowly drift, scale, and morph behind the content. Uses `filter: blur()` on multiple colored divs with keyframe animations.

**How it works:** Three overlapping `div` elements positioned fixed behind the UI with `pointer-events: none`. Each has a `border-radius: 50%`, a warm color from the design palette, and an independent `@keyframes` animation that slowly moves them in large looping paths. A sibling `backdrop-filter` layer sits on top to keep the effect from washing out text. The whole stack is behind the chat surface.

**Bundle impact:** 0kb — all CSS.

```css
/* Core concept */
.fx-blob {
  position: fixed;
  inset: -50%;
  z-index: -2;
  filter: blur(80px);
  opacity: 0.15;
  animation: blob-drift 30s ease-in-out infinite;
}
.fx-blob:nth-child(1) {
  background: #f5f2ef;
  animation-duration: 35s;
}
.fx-blob:nth-child(2) {
  background: #e8e4e0;
  animation-duration: 28s;
  animation-delay: -10s;
}
@keyframes blob-drift {
  0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); }
  33% { transform: translate(30%, -20%) scale(1.1) rotate(120deg); }
  66% { transform: translate(-20%, 30%) scale(0.9) rotate(240deg); }
}
```

Dark mode adjustment: swap to `#22201e` / `#2a2520` at `opacity: 0.1`.

**Pros:** Zero JS, zero deps, works immediately, respects reduced-motion.
**Cons:** Less controllable than canvas/JS; limited to blur shapes.

---

## 2. Canvas Particle Mist

**Library:** None (raw Canvas API)

**Description:** 100-200 tiny dots floating upward at very low opacity. In light mode: warm stone specks at 4-6% opacity. In dark mode: white specks at 3-5%. Simulates dust motes in sunlight.

**How it works:** A `<canvas>` element positioned fixed behind the chat. A particle array stores `{x, y, vx, vy, radius, alpha, life}` for each particle. On each `requestAnimationFrame` frame, particles drift upward with slight horizontal sway, fade in/out smoothly, and recycle when they exit the top of the viewport (respawn at bottom with random x).

```typescript
interface Particle {
  x: number; y: number;
  vx: number; vy: number;
  radius: number;
  alpha: number;
  life: number; // 0-1, lerped
}

const PARTICLES = 120;
const BASE_SPEED = 0.15; // px per frame — barely perceptible

function update(particles: Particle[], ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  for (const p of particles) {
    p.y -= p.vy;
    p.x += Math.sin(p.y * 0.01) * 0.3; // gentle sway
    if (p.y < -10) { p.y = ctx.canvas.height + 10; p.x = Math.random() * ctx.canvas.width; }
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(119, 113, 105, ${p.alpha})`; // warm stone
    ctx.fill();
  }
}
```

**Theme adaptation:** Read `--text-subtle` or `--text-muted` from CSS custom properties via `getComputedStyle` and use it as the particle color. In dark mode the same approach works — the CSS variable changes, the canvas follows.

**Pros:** Zero deps, ~50 lines, fully controllable, easy to theme.
**Cons:** Canvas doesn't automatically respond to CSS variable changes — need a `MutationObserver` or theme-toggle hook to re-read colors.

---

## 3. Canvas Data Flow

**Library:** None (raw Canvas API)

**Description:** Abstract neural-signal-like lines that drift horizontally across the screen. Thin strokes at 2-5% opacity, no sharp edges — more like faint light trails than literal neurons. Thematic for an AI reasoning pipeline.

**How it works:** A growing/shrinking pool of bezier curves that animate their control points. Each "signal" is a multi-segment curved line with a gradient fade at both ends. Signals travel from left to right (or right to left) at a slow, steady pace.

```typescript
// Each signal is a series of connected points with easing
interface Signal {
  points: { x: number; y: number; cp: { x: number; y: number } }[];
  progress: number; // 0-1, signal's position along the path
  speed: number;
  pathCount: number;
}

function drawSignal(ctx: CanvasRenderingContext2D, s: Signal) {
  ctx.beginPath();
  ctx.moveTo(s.points[0].x, s.points[0].y);
  for (let i = 1; i < s.points.length; i++) {
    ctx.bezierCurveTo(
      s.points[i-1].cp.x, s.points[i-1].cp.y,
      s.points[i].cp.x, s.points[i].cp.y,
      s.points[i].x, s.points[i].y
    );
  }
  ctx.strokeStyle = `rgba(119, 113, 105, ${0.02 + s.progress * 0.03})`;
  ctx.lineWidth = 1;
  ctx.stroke();
}
```

**Signal count:** Keep at 3-5 simultaneous signals to avoid visual clutter.

**Pros:** Thematic, zero deps, distinctive.
**Cons:** More complex particle math; risk of looking like a generic "tech background."

---

## 4. CSS Film Grain Noise

**Library:** None (CSS + inline SVG or base64)

**Description:** A subtle animated noise texture overlaid at ~2% opacity. Adds tactile warmth — like a slightly imperfect analog surface. Barely perceptible unless you look for it, but the absence is felt when it's gone.

**How it works:** A fixed-position pseudo-element or div with a repeating noise SVG/PNG as background, animated with tiny `transform` shifts to create the "alive" grain feel.

```css
.fx-grain {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  opacity: 0.02;
  background-image: url("data:image/svg+xml,..."); /* tiny noise pattern */
  background-repeat: repeat;
  background-size: 128px 128px;
  animation: grain-shift 0.5s steps(3) infinite;
}

@keyframes grain-shift {
  0% { transform: translate(0, 0); }
  33% { transform: translate(-1px, 1px); }
  66% { transform: translate(1px, -1px); }
  100% { transform: translate(0, 0); }
}
```

**Noise SVG approach:** Generate a 128x128 SVG with random `<rect>` elements at varying opacities, data-URI it as the background image. The base64 noise can be inlined in CSS to avoid an extra HTTP request.

Alternatively, use the CSS `filter: contrast(1000%) brightness(0%)` trick on a randomly seeded SVG `feTurbulence` filter — but this is less portable across browsers.

**Pros:** Trivial, zero JS, works everywhere, complements any other effect.
**Cons:** The "steps(3)" animation can feel janky on some browsers; the subtlety means users won't consciously notice it (which is the goal, but makes it hard to demo).

---

## 5. @react-three/fiber Particle Field

**Library:** `@react-three/fiber` + `@react-three/drei`

**Description:** Thousands of tiny 3D points arranged in a sparse cloud, slowly rotating as a group. Each point is a single-vertex sprite with rounded shape. The camera orbits imperceptibly slowly, creating the sense of being inside a vast but very dim data field.

**How it works:** A React component using `<Canvas>` from R3F, positioned fixed behind the UI with `pointer-events: none`. The particle geometry uses `THREE.BufferGeometry` with random positions in a sphere/box distribution. Each particle is rendered as a `<Points>` / `<PointMaterial>` from drei.

```tsx
'use client';
import { Canvas, useFrame } from '@react-three/fiber';
import { Points, PointMaterial } from '@react-three/drei';
import { useRef, useMemo } from 'react';

function ParticleCloud() {
  const ref = useRef<THREE.Points>(null!);
  const positions = useMemo(() => {
    const pos = new Float32Array(2000 * 3);
    for (let i = 0; i < 2000; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 40;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 40;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 40;
    }
    return pos;
  }, []);

  useFrame((_, delta) => {
    ref.current.rotation.y += delta * 0.02;
    ref.current.rotation.x += delta * 0.005;
  });

  return (
    <Points ref={ref} positions={positions} stride={3} frustumCulled={false}>
      <PointMaterial
        transparent
        color="#777169"
        size={0.08}
        sizeAttenuation
        depthWrite={false}
        opacity={0.4}
      />
    </Points>
  );
}

export function FXParticles() {
  return (
    <div className="fixed inset-0 -z-10 pointer-events-none">
      <Canvas camera={{ position: [0, 0, 15], fov: 60 }}>
        <ParticleCloud />
      </Canvas>
    </div>
  );
}
```

**Bundle impact:** ~150kb gzip (r3f + drei + three). Use dynamic import:
```tsx
const FXParticles = dynamic(() => import('@/components/fx/FXParticles'), { ssr: false });
```

**Pros:** Stunning visual; feels high-effort and premium; 3D depth is unique.
**Cons:** Heavy bundle; WebGL can drain battery on mobile; must be careful with mobile detection/disabling.

---

## 6. @react-three/fiber Wireframe Geometry

**Library:** `@react-three/fiber` + `@react-three/drei`

**Description:** A single low-poly wireframe shape (torus knot, icosahedron, or Möbius strip) rendered at very low opacity, slowly rotating in the background center. Out of focus, barely there. The geometric form echoes "reasoning" and "architecture" conceptually.

```tsx
function WireframeShape() {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame((_, delta) => {
    ref.current.rotation.x += delta * 0.1;
    ref.current.rotation.y += delta * 0.15;
  });
  return (
    <mesh ref={ref}>
      <torusKnotGeometry args={[2, 0.6, 64, 8]} />
      <meshBasicMaterial
        wireframe
        color="#777169"
        transparent
        opacity={0.06}
      />
    </mesh>
  );
}
```

**Positioning:** Centered in viewport, scaled to ~30% of viewport height. The wireframe is so faint it reads as an ambient texture rather than a distinct object.

**Bundle impact:** Same as #5 — ~150kb gzip.

**Pros:** Strong thematic resonance (structured reasoning); very low visual weight despite 3D.
**Cons:** Same bundle concerns as particle field; fixed central position may conflict with content on some screen sizes.

---

## 7. CSS + Canvas Mesh Gradient

**Library:** None

**Description:** A smooth, slowly morphing gradient field rendered to canvas using bilinear interpolation between randomly moving color points. Unlike CSS blob approach (which uses blur), this is calculated per-pixel on a small offscreen canvas then upscaled — giving it a different quality of motion.

**How it works:** Maintain a 4x4 or 6x6 grid of color control points. Each has a `(x, y)` position and a color from the warm palette. On each frame, control points drift via simplex noise or random walk. The canvas renders by bilinearly interpolating between the control points. Because the grid is small, the per-frame cost is negligible. The result is a fluid, organic color wash.

```typescript
interface ColorPoint {
  x: number; y: number;
  r: number; g: number; b: number;
  vx: number; vy: number;
}

function renderMesh(ctx: CanvasRenderingContext2D, grid: ColorPoint[][]) {
  const w = ctx.canvas.width, h = ctx.canvas.height;
  // For each pixel, find containing quad and bilinearly blend
  // ... (bilinear interpolation between 4 nearest control points)
}
```

**Performance optimization:** Render at 1/4 resolution, then `ctx.imageSmoothingEnabled = true` and `drawImage` at full size. The upscale blur hides pixel-level artifacts.

**Theme adaptation:** Warm stone palette in light mode (`#f5f2ef` → `#e8e4e0` → `#f5f5f5`). Deep warm charcoal in dark mode (`#1a1817` → `#22201e` → `#141414`).

**Pros:** Zero deps, uniquely organic, responsive to theme.
**Cons:** Slightly more complex math than blob approach; canvas sizing needs resize observer.

---

## 8. GSAP Morphing Shapes

**Library:** `gsap`

**Description:** Two or three abstract SVG paths that slowly morph their shapes over 10-20 second intervals. The paths are simple — rounded blobs, soft curves — rendered at low opacity with warm stroke/fill colors.

**How it works:** Define start/end SVG path data arrays and animate between them using GSAP's `morphSVG` plugin or manual attribute interpolation.

```typescript
import { gsap } from 'gsap';

const paths = [
  'M0,100 C30,20 70,20 100,100 C130,180 170,180 200,100...',
  'M0,150 C40,40 60,160 100,100 C140,40 160,160 200,100...',
];

// Animate between shapes
gsap.to('#morphing-path', {
  attr: { d: paths[1] },
  duration: 15,
  repeat: -1,
  yoyo: true,
  ease: 'sine.inOut',
});
```

**Bundle impact:** ~30kb gzip (GSAP core + MorphSVGPlugin).

**Pros:** Smooth, declarative, great easing curves, easy to combine with scroll triggers.
**Cons:** 30kb for what's essentially two animated blobs is heavy; MorphSVGPlugin is a paid GSAP membership feature.

---

## Integration Patterns (All Approaches)

### Common setup

```tsx
// Wrapper component pattern — applies to any of the above
export function BackgroundFX({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative">
      {/* FX canvas/element injected here, positioned fixed/absolute behind */}
      {children}
    </div>
  );
}
```

### Reduced motion respect

All animated effects must check `prefers-reduced-motion`:

```typescript
const prefersReducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false;

if (prefersReducedMotion) {
  // Render static frame instead of animation loop
}
```

### Dark mode awareness

Canvas-based effects should re-read CSS variables on theme change:

```typescript
const observer = new MutationObserver(() => {
  const isDark = document.documentElement.classList.contains('dark');
  // re-initialize colors
});
observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
```

### Mobile / battery strategy

Heavy effects (WebGL, canvas with many particles) should disable on low-power or mobile:

```typescript
const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
const prefersReduced = ...; // matchMedia above

if (isMobile || prefersReduced || navigator?.connection?.saveData) {
  // Don't render, or render CSS-only fallback
}
```

---

## Recommendation Matrix

| Effect | Visual Impact | Dev Cost | Performance | Best For |
|--------|:---:|:--------:|:---:|---------|
| **CSS Blobs** | ★★★ | ~15min | Excellent | Quick win, lowest effort |
| **Canvas Particles** | ★★★★ | ~1hr | Excellent | Best quality/efficiency ratio |
| **Canvas Data Flow** | ★★★ | ~2hrs | Good | Thematic tie-in to AI |
| **CSS Film Grain** | ★★ | ~10min | Excellent | Layer on top of any other effect |
| **R3F Particles** | ★★★★★ | ~2hrs | Moderate | Premium flagship effect |
| **R3F Wireframe** | ★★★★ | ~1.5hrs | Moderate | Conceptual depth, lower particle cost |
| **Mesh Gradient** | ★★★★ | ~2hrs | Good | Fluid, organic, warm |
| **GSAP Morph** | ★★★ | ~1hr | Excellent | If GSAP is already used |

### Suggested layering strategy

```
Layer 1: Film grain noise  (always on, trivial)
Layer 2: CSS blobs OR Canvas particles  (choose one, medium effort)
Layer 3: R3F field (premium enhancement, dynamic import, desktop only)
```

This way the base experience always has some texture, and WebGL is progressive enhancement.
