'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

/**
 * An infinite horizontal marquee of arbitrary nodes.
 *
 * Adapted from React Bits' LogoLoop (MIT + Commons Clause, David Haz —
 * reactbits.dev). Upstream is ~500 lines because it also does vertical
 * scrolling, `<img>` items with a load-coordination hook, a `renderItem`
 * escape hatch, and per-item hover scaling. None of that survives contact
 * with this codebase: there are no logo image assets in the repo, the CSP is
 * `default-src 'self'` so third-party logo CDNs are dead on arrival anyway,
 * and a wordmark set in the page's own type is the honest version of a "logos
 * we work with" strip. What is left is the part that was worth taking — the
 * measure-and-duplicate trick and the smoothed velocity loop.
 *
 * Three changes beyond the trim:
 *
 * 1. Hover is a ref, not state. Upstream re-runs the whole animation effect on
 *    every mouse enter and leave, which tears down and rebuilds the rAF loop
 *    mid-scroll; here it only retargets the velocity the running loop is
 *    easing toward.
 * 2. The loop is gated on IntersectionObserver *and* `visibilitychange`, the
 *    same pairing DisagreementField uses a few elements up the page — a
 *    backgrounded tab keeps its intersection ratio, so the observer alone
 *    would leave this running behind whatever the reader switched to.
 * 3. Under `prefers-reduced-motion` this renders a static wrapped list rather
 *    than a frozen marquee. Upstream freezes the track in place, which leaves
 *    every name past the container's width clipped and unreachable — the
 *    reader who asked for stillness is the one who ends up seeing least.
 */

export interface LogoLoopProps {
  /** Rendered in order, then duplicated as many times as it takes to fill. */
  items: readonly ReactNode[];
  /** Scroll rate in pixels per second. */
  speed?: number;
  /** Horizontal space between items, in pixels. Also the measured unit. */
  gap?: number;
  /** Ease to a standstill while the pointer is over the strip. */
  pauseOnHover?: boolean;
  /** Colour the edge fades resolve to. Must match the ground behind the strip. */
  fadeColor?: string;
  /** Required: the strip is a landmark, and an unlabelled one is noise. */
  ariaLabel: string;
  className?: string;
}

/** Seconds for the velocity to close most of the gap to its target. */
const SMOOTHING_TAU = 0.25;

/** Copies beyond the ones strictly needed to cover the container. */
const COPY_HEADROOM = 2;

export function LogoLoop({
  items,
  speed = 40,
  gap = 48,
  pauseOnHover = true,
  fadeColor = 'var(--bg)',
  ariaLabel,
  className,
}: LogoLoopProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef<HTMLUListElement>(null);
  const hoveredRef = useRef(false);

  const [seqWidth, setSeqWidth] = useState(0);
  const [copyCount, setCopyCount] = useState(2);

  const reducedMotion = usePrefersReducedMotion();

  /* Measure one sequence and work out how many copies cover the container.
     Two observers because the two boxes change size for unrelated reasons:
     the container tracks the viewport, the sequence tracks font loading. */
  useEffect(() => {
    if (reducedMotion) return;
    const container = containerRef.current;
    const seq = seqRef.current;
    if (!container || !seq) return;

    const measure = () => {
      const width = seq.getBoundingClientRect().width;
      if (width <= 0) return;
      setSeqWidth(Math.ceil(width));
      setCopyCount(
        Math.max(2, Math.ceil(container.clientWidth / width) + COPY_HEADROOM)
      );
    };

    const observer = new ResizeObserver(measure);
    observer.observe(container);
    observer.observe(seq);
    measure();

    /* A webfont swap resizes the sequence after layout has settled. The
       ResizeObserver catches that, but only once the font has actually
       landed, and on a cold load that can be after the first measure. */
    document.fonts?.ready.then(measure).catch(() => {});

    return () => observer.disconnect();
  }, [reducedMotion, items, gap]);

  /* Advance the track. Offset wraps modulo one sequence width, so the strip
     never accumulates a transform large enough to lose sub-pixel precision. */
  useEffect(() => {
    if (reducedMotion || seqWidth <= 0) return;
    const track = trackRef.current;
    const container = containerRef.current;
    if (!track || !container) return;

    let frame = 0;
    let visible = true;
    let offset = 0;
    let velocity = 0;
    let last: number | null = null;

    const loop = (time: number) => {
      frame = window.requestAnimationFrame(loop);
      if (last === null) last = time;
      const delta = Math.max(0, time - last) / 1000;
      last = time;

      const target = pauseOnHover && hoveredRef.current ? 0 : speed;
      /* Frame-rate independent exponential ease, so a 120Hz display and a
         60Hz one reach the same speed in the same wall-clock time. */
      velocity += (target - velocity) * (1 - Math.exp(-delta / SMOOTHING_TAU));

      offset = (offset + velocity * delta) % seqWidth;
      track.style.transform = `translate3d(${-offset}px, 0, 0)`;
    };

    const stop = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = 0;
      /* Dropped so the compositor can release the layer while parked. */
      track.style.willChange = '';
      last = null;
    };

    const start = () => {
      stop();
      track.style.willChange = 'transform';
      frame = window.requestAnimationFrame(loop);
    };

    /* Paused off-screen and in a backgrounded tab. IntersectionObserver alone
       misses the second: a hidden tab keeps its intersection ratio. */
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (visible && !document.hidden) start();
        else stop();
      },
      { threshold: 0.01 }
    );

    const onVisibility = () => {
      if (!document.hidden && visible) start();
      else stop();
    };

    start();
    observer.observe(container);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      observer.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [reducedMotion, seqWidth, speed, pauseOnHover]);

  if (reducedMotion) {
    return (
      <div className={className} role="region" aria-label={ariaLabel}>
        <ul
          className="flex flex-wrap items-center justify-center"
          style={{ columnGap: `${gap}px`, rowGap: `${Math.round(gap / 3)}px` }}
        >
          {items.map((node, index) => (
            <li key={index}>{node}</li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn('relative overflow-x-hidden', className)}
      role="region"
      aria-label={ariaLabel}
      onMouseEnter={() => {
        hoveredRef.current = true;
      }}
      onMouseLeave={() => {
        hoveredRef.current = false;
      }}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-0 z-10 w-[clamp(2rem,8%,6rem)]"
        style={{ background: `linear-gradient(to right, ${fadeColor}, transparent)` }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 right-0 z-10 w-[clamp(2rem,8%,6rem)]"
        style={{ background: `linear-gradient(to left, ${fadeColor}, transparent)` }}
      />

      <div ref={trackRef} className="flex w-max select-none">
        {Array.from({ length: copyCount }, (_, copy) => (
          <ul
            key={copy}
            ref={copy === 0 ? seqRef : undefined}
            /* Copies past the first are the same names again; a screen reader
               reading the strip N times over is worse than not reading it. */
            aria-hidden={copy > 0}
            className="flex shrink-0 items-center"
            style={{ columnGap: `${gap}px`, paddingRight: `${gap}px` }}
          >
            {items.map((node, index) => (
              <li key={index} className="shrink-0">
                {node}
              </li>
            ))}
          </ul>
        ))}
      </div>
    </div>
  );
}

export default LogoLoop;
