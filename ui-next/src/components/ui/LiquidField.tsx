'use client';

import { motion } from 'framer-motion';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

interface Blob {
  size: number;
  color: string;
  /** Static top-left corner (%) — set once, never animated. */
  base: { top: string; left: string };
  /** Drift keyframes as transform offsets in px from `base`. Compositor-only:
   *  `top`/`left` never change after mount, so this never triggers layout. */
  drift: Array<{ x: number; y: number }>;
  duration: number;
  delay: number;
}

/**
 * Four blobs of decreasing opacity so no single one reads as a hard shape —
 * the gooey merge does that work instead. `color-mix` over --accent inherits
 * Workstream A's re-hue for free; no light/dark branch needed here.
 */
// Kept deliberately subtle — this sits directly behind the hero heading, and
// the hero's vignette (LandingPage.tsx) is *most* transparent at dead center,
// right where the text is, not least. Peak opacity here plus that vignette
// must not cost the heading its measured contrast margin from Workstream A.
const BLOBS: Blob[] = [
  {
    size: 220,
    color: 'color-mix(in oklab, var(--accent) 16%, transparent)',
    base: { top: '20%', left: '25%' },
    drift: [
      { x: 0, y: 0 },
      { x: 60, y: 40 },
      { x: 20, y: 70 },
      { x: 0, y: 0 },
    ],
    duration: 22,
    delay: 0,
  },
  {
    size: 260,
    color: 'color-mix(in oklab, var(--accent) 12%, transparent)',
    base: { top: '55%', left: '15%' },
    drift: [
      { x: 0, y: 0 },
      { x: 50, y: -30 },
      { x: 90, y: 10 },
      { x: 0, y: 0 },
    ],
    duration: 27,
    delay: 3,
  },
  {
    size: 180,
    color: 'color-mix(in oklab, var(--accent) 9%, transparent)',
    base: { top: '65%', left: '60%' },
    drift: [
      { x: 0, y: 0 },
      { x: -40, y: -50 },
      { x: -70, y: 10 },
      { x: 0, y: 0 },
    ],
    duration: 24,
    delay: 6,
  },
  {
    size: 150,
    color: 'color-mix(in oklab, var(--accent) 7%, transparent)',
    base: { top: '12%', left: '55%' },
    drift: [
      { x: 0, y: 0 },
      { x: -50, y: 40 },
      { x: -90, y: -10 },
      { x: 0, y: 0 },
    ],
    duration: 20,
    delay: 1.5,
  },
];

/**
 * Decorative ambient background layer. One per viewport — see plan §C.5;
 * two overlapping full-bleed gooey layers is a dropped-frame generator on
 * integrated graphics.
 *
 * `top`/`left` place each blob once and never animate — only `x`/`y`
 * (framer-motion transform offsets) move afterward, so the loop stays on
 * the compositor thread. Never animate `stdDeviation` on the shared `#goo`
 * filter: that forces a filter-region recompute every frame.
 */
export function LiquidField() {
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div
      aria-hidden="true"
      className="contain-layout-paint pointer-events-none absolute inset-0 z-0 overflow-hidden"
      style={{ filter: 'url(#goo)' }}
    >
      {BLOBS.map((blob, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{
            width: blob.size,
            height: blob.size,
            background: blob.color,
            top: blob.base.top,
            left: blob.base.left,
          }}
          animate={
            prefersReducedMotion
              ? { x: 0, y: 0 }
              : { x: blob.drift.map((d) => d.x), y: blob.drift.map((d) => d.y) }
          }
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: blob.duration, delay: blob.delay, repeat: Infinity, ease: 'easeInOut' }
          }
        />
      ))}
    </div>
  );
}
