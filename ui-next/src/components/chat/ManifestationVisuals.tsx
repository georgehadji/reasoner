'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

interface ManifestationVisualsProps {
  progress: number; // 0 to 1
}

const RING_BORDER = '1px solid color-mix(in oklab, var(--accent) 35%, transparent)';

/**
 * Expanding rings. `delay` drives the animated version; `staticSize` /
 * `staticOpacity` are the frozen concentric snapshot rendered instead when the
 * user has asked for reduced motion.
 */
const RINGS = [
  { delay: 0, staticSize: 20, staticOpacity: 0.45 },
  { delay: 0.6, staticSize: 36, staticOpacity: 0.28 },
  { delay: 1.2, staticSize: 52, staticOpacity: 0.14 },
] as const;

/**
 * Decorative scanner panel shown while an image is being generated.
 *
 * Purely ornamental: it never intercepts pointer events, it is hidden from
 * assistive tech, and `contain: layout paint` keeps the scan line's per-frame
 * invalidation inside this box instead of the whole page.
 *
 * Under `prefers-reduced-motion` none of the ambient loops run — the panel
 * renders as a static composition. The progress fill still tracks `progress`,
 * because that is data, not ambience; it just snaps instead of easing.
 */
export function ManifestationVisuals({ progress }: ManifestationVisualsProps) {
  // Reduced-motion users see at most a single animated frame before the
  // static composition below takes over.
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div
      className="contain-layout-paint pointer-events-none relative h-52 w-full overflow-hidden rounded-lg"
      aria-hidden="true"
      style={{
        background: 'var(--surface-3)',
        border: '1px solid var(--border-strong)',
      }}
    >
      {/* Dot grid */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'radial-gradient(circle, color-mix(in oklab, var(--accent) 12%, transparent) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          opacity: 0.6,
        }}
      />

      {/* Progress fill — rises from bottom */}
      <motion.div
        className="absolute bottom-0 left-0 right-0"
        style={{
          background:
            'linear-gradient(to top, color-mix(in oklab, var(--accent) 7%, transparent) 0%, transparent 100%)',
        }}
        animate={{ height: `${progress * 100}%` }}
        transition={{ duration: prefersReducedMotion ? 0 : 0.4, ease: 'linear' }}
      />

      {/* Scan line — sweeps top to bottom, parked at the top when reduced */}
      {prefersReducedMotion ? (
        <div
          className="absolute left-0 right-0 h-px"
          style={{
            top: 0,
            background:
              'linear-gradient(90deg, transparent 0%, color-mix(in oklab, var(--accent) 60%, transparent) 20%, var(--accent) 50%, color-mix(in oklab, var(--accent) 60%, transparent) 80%, transparent 100%)',
            boxShadow: '0 0 8px 1px color-mix(in oklab, var(--accent) 30%, transparent)',
          }}
        />
      ) : (
        <motion.div
          className="absolute left-0 right-0 h-px"
          style={{
            background:
              'linear-gradient(90deg, transparent 0%, color-mix(in oklab, var(--accent) 60%, transparent) 20%, var(--accent) 50%, color-mix(in oklab, var(--accent) 60%, transparent) 80%, transparent 100%)',
            boxShadow: '0 0 8px 1px color-mix(in oklab, var(--accent) 30%, transparent)',
          }}
          animate={{ top: ['0%', '100%'] }}
          transition={{ duration: 2.8, repeat: Infinity, ease: 'linear' }}
        />
      )}

      {/* Corner markers */}
      {[
        { top: 10, left: 10, rotate: 0 },
        { top: 10, right: 10, rotate: 90 },
        { bottom: 10, right: 10, rotate: 180 },
        { bottom: 10, left: 10, rotate: 270 },
      ].map((pos, i) => (
        <div
          key={i}
          className="absolute h-4 w-4"
          style={{
            ...pos,
            rotate: `${pos.rotate}deg`,
            opacity: 0.35,
          }}
        >
          <div
            className="absolute top-0 left-0 h-px w-3"
            style={{ background: 'var(--accent)' }}
          />
          <div
            className="absolute top-0 left-0 h-3 w-px"
            style={{ background: 'var(--accent)' }}
          />
        </div>
      ))}

      {/* Center — pulsing dot with rings */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative flex items-center justify-center">
          {/* Rings */}
          {RINGS.map(({ delay, staticSize, staticOpacity }, i) =>
            prefersReducedMotion ? (
              <div
                key={i}
                className="absolute rounded-full"
                style={{
                  border: RING_BORDER,
                  width: staticSize,
                  height: staticSize,
                  opacity: staticOpacity,
                }}
              />
            ) : (
              <motion.div
                key={i}
                className="absolute rounded-full"
                style={{ border: RING_BORDER }}
                initial={{ width: 12, height: 12, opacity: 0.5 }}
                animate={{ width: 56, height: 56, opacity: 0 }}
                transition={{
                  duration: 2.4,
                  repeat: Infinity,
                  delay,
                  ease: 'easeOut',
                }}
              />
            ),
          )}

          {/* Core dot */}
          {prefersReducedMotion ? (
            <div
              className="relative z-10 h-2 w-2 rounded-full"
              style={{ background: 'var(--accent)' }}
            />
          ) : (
            <motion.div
              className="relative z-10 h-2 w-2 rounded-full"
              style={{ background: 'var(--accent)' }}
              animate={{ opacity: [0.6, 1, 0.6] }}
              transition={{ duration: 1.8, repeat: Infinity }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
