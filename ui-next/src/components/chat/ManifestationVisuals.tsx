'use client';

import React from 'react';

interface ManifestationVisualsProps {
  progress: number; // 0 to 1
}

/**
 * The slot the generated image will fill, shown while it is made. A flat
 * field rises with `progress`; that is the only signal, because it is data.
 * The scanner ornaments it once carried (dot grid, glowing scan line, crop
 * marks, pulsing rings) said "working" without saying anything true.
 *
 * Hidden from assistive tech: ChatFeed's progressbar carries the value.
 * Reduced motion keeps the fill and drops the easing.
 */
export function ManifestationVisuals({ progress }: ManifestationVisualsProps) {
  return (
    <div
      className="pointer-events-none relative h-52 w-full overflow-hidden rounded-[var(--radius-lg)] bg-[var(--surface-3)]"
      aria-hidden="true"
    >
      <div
        className="absolute inset-x-0 bottom-0 bg-[var(--accent-dim)] transition-[height] duration-[var(--dur-state)] ease-linear motion-reduce:transition-none"
        style={{ height: `${Math.min(1, Math.max(0, progress)) * 100}%` }}
      />
    </div>
  );
}
