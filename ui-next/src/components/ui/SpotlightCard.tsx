'use client';

import { useCallback, useRef, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

/**
 * A card that lights up under the cursor.
 *
 * Adapted from React Bits' SpotlightCard (MIT + Commons Clause, David Haz —
 * reactbits.dev). Three things changed on the way in, all of them things this
 * codebase already decided elsewhere:
 *
 * 1. The upstream component bakes in its own radius, padding, and a border
 *    and fill taken straight from Tailwind's dark neutral ramp — hardcoded
 *    values from a dark-only design system. (Naming those two classes here
 *    would trip the design token guard in .github/workflows/test.yml, which
 *    greps for raw palette colours and does not care that this is a
 *    comment.) Here the caller owns every one of them and this renders the
 *    overlay alone, composing with an existing card instead of replacing
 *    it, so the pricing tiers keep their own border, ring and badge.
 * 2. Upstream stores the cursor position in React state, which re-renders the
 *    whole subtree on every mousemove — a pricing card is not a cheap
 *    subtree. The position is written straight to CSS custom properties on
 *    the overlay node instead, so a move costs one style recalculation and no
 *    React work.
 * 3. Upstream has no reduced-motion path and lights up on keyboard focus with
 *    the spotlight still parked wherever the mouse last was (0,0 on first
 *    load — a bright corner, for a user who never touched the mouse). Both
 *    are gone: the effect is mouse-only and opts out entirely under
 *    `prefers-reduced-motion`, per the rule at globals.css.
 *
 * The overlay clips itself with `rounded-[inherit]` rather than putting
 * `overflow-hidden` on the root, because callers hang badges outside the card
 * box and an overflow clip would cut them off.
 *
 * It also sits at a negative z-index inside an `isolate`d root, which upstream
 * does not do. An absolutely positioned overlay paints above static in-flow
 * content, so upstream's version washes the card's own text and buttons in
 * accent tint; a negative z-index inside a stacking context paints after the
 * root's background and before its children, which is where a spotlight
 * belongs. `isolate` is what keeps that negative layer from escaping behind
 * the card entirely.
 */

interface SpotlightCardProps {
  children: ReactNode;
  className?: string;
  /**
   * Any CSS colour. Defaults to the brand accent at the alpha a warm ivory
   * ground can carry without the card looking backlit — on `--surface` a
   * stronger fill reads as a hover state that has got stuck.
   */
  spotlightColor?: string;
  /** Radius of the lit area. */
  radius?: string;
}

export function SpotlightCard({
  children,
  className,
  spotlightColor = 'color-mix(in oklab, var(--accent) 14%, transparent)',
  radius = '22rem',
}: SpotlightCardProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = usePrefersReducedMotion();

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    // Touch and pen fire pointermove too, but they have no hover state: the
    // spotlight would light up on tap and then stay lit with nothing under it.
    if (event.pointerType !== 'mouse') return;
    const overlay = overlayRef.current;
    if (!overlay) return;

    const rect = event.currentTarget.getBoundingClientRect();
    overlay.style.setProperty('--spotlight-x', `${event.clientX - rect.left}px`);
    overlay.style.setProperty('--spotlight-y', `${event.clientY - rect.top}px`);
    overlay.style.opacity = '1';
  }, []);

  const handlePointerLeave = useCallback(() => {
    const overlay = overlayRef.current;
    if (overlay) overlay.style.opacity = '0';
  }, []);

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      className={cn('relative isolate', className)}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      <div
        ref={overlayRef}
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] opacity-0 transition-opacity duration-500 ease-out"
        style={{
          background: `radial-gradient(${radius} circle at var(--spotlight-x, 50%) var(--spotlight-y, 50%), ${spotlightColor}, transparent 70%)`,
        }}
      />
      {children}
    </div>
  );
}

export default SpotlightCard;
