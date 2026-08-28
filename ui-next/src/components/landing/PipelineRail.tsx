'use client';

import { useEffect, useRef } from 'react';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

/**
 * The rail above the four stages, animated — and, like the masthead field, an
 * argument rather than an ornament.
 *
 * A packet enters at the left and crosses the four stage nodes. What happens
 * to it at each node is the actual behaviour of that stage, not a generic
 * flow effect:
 *
 *   01 Routing    one packet becomes four — the models chosen for this run
 *   02 Reasoning  the four run in fixed parallel lanes and never touch,
 *                 which is the propagation defence drawn rather than claimed
 *   03 Critique   each is marked by a scorer it did not arrive with
 *   04 Labelling  they resolve into the three epistemic colours
 *
 * The lanes in stage 03 are the load-bearing detail. The obvious animation —
 * particles converging into one stream — would depict the opposite of what
 * the pipeline does, and would contradict §3 in the same viewport that
 * introduces it. Nothing here ever merges.
 *
 * 2D canvas, matching DisagreementField for the same reason: at this element
 * count a shader buys nothing visible and costs a context that can be lost,
 * blocklisted, or refused. This always paints. Desktop only — the stages
 * stack on a phone, and a left-to-right rail drawn over a vertical stack
 * would be a picture of a flow that is not on screen.
 */

/** One per generator in a Premium preset — the cross-lab floor is four. */
const LANES = 4;

/** Seconds for one packet to cross the whole rail. Slow enough to read. */
const CROSSING_MS = 9000;
const FRAME_MS = 1000 / 30;

/** Retina buys nothing on hairlines and 4px squares, and costs 4x the fill. */
const MAX_DPR = 1.5;

/** Re-read theme tokens about twice a second — cheap, and survives a toggle. */
const PALETTE_EVERY = 15;

interface Palette {
  rail: string;
  node: string;
  packet: string;
  verified: string;
  hypothesis: string;
  unknown: string;
}

function readPalette(el: HTMLElement): Palette {
  const cs = getComputedStyle(el);
  const read = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  return {
    rail: read('--border-strong', '#8884'),
    node: read('--accent', '#2F3832'),
    packet: read('--text-subtle', '#606963'),
    verified: read('--ok', '#2E449F'),
    hypothesis: read('--warn', '#7B4193'),
    unknown: read('--unknown', '#2C697D'),
  };
}

/** Stage node centres, as a fraction of width — the grid's column centres. */
const NODES = Array.from({ length: 4 }, (_, i) => (i + 0.5) / 4);

/**
 * Vertical offset of a lane, in pixels from the rail. Fixed per lane and
 * never interpolated toward zero: these four do not converge.
 */
function laneOffset(lane: number, height: number): number {
  const spread = Math.min(height * 0.3, 22);
  return (lane - (LANES - 1) / 2) * (spread / ((LANES - 1) / 2));
}

function draw(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  palette: Palette,
  progress: number,
): void {
  const midY = height / 2;
  ctx.clearRect(0, 0, width, height);

  /* The rail itself. */
  ctx.strokeStyle = palette.rail;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, Math.round(midY) + 0.5);
  ctx.lineTo(width, Math.round(midY) + 0.5);
  ctx.stroke();

  /* Stage nodes, each dropping a hairline into the column it belongs to.
     Without the drop the rail and the four stage descriptions read as two
     unrelated registers; with it they are one diagram. */
  for (const at of NODES) {
    const nx = Math.round(at * width);
    ctx.strokeStyle = palette.rail;
    ctx.beginPath();
    ctx.moveTo(nx + 0.5, Math.round(midY) + 3);
    ctx.lineTo(nx + 0.5, height);
    ctx.stroke();

    ctx.fillStyle = palette.node;
    ctx.fillRect(nx - 2, Math.round(midY) - 2, 5, 5);
  }

  /* How many nodes the packet has already passed. */
  const x = progress * width;
  const passed = NODES.filter((at) => x >= at * width).length;

  const drawSquare = (cx: number, cy: number, size: number, fill: string) => {
    ctx.fillStyle = fill;
    ctx.fillRect(Math.round(cx) - size / 2, Math.round(cy) - size / 2, size, size);
  };

  if (passed === 0) {
    /* One packet, before routing has chosen anything. */
    drawSquare(x, midY, 4, palette.packet);
    return;
  }

  const epistemic = [palette.verified, palette.hypothesis, palette.verified, palette.unknown];

  for (let lane = 0; lane < LANES; lane += 1) {
    /* Lanes open up over the segment following stage 01 rather than
       snapping apart at it. */
    const openFrom = NODES[0] * width;
    const openTo = NODES[1] * width;
    const opening = Math.min(1, Math.max(0, (x - openFrom) / (openTo - openFrom)));
    const y = midY + laneOffset(lane, height) * opening;

    drawSquare(x, y, 4, passed >= 4 ? epistemic[lane] : palette.packet);

    /* The critic's mark, applied at stage 03 and carried onward. */
    if (passed >= 3) {
      drawSquare(x - 7, y, 2, palette.node);
    }
  }
}

export function PipelineRail() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let palette = readPalette(canvas);

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);

    /* A reader who asked for stillness gets the finished state — the four
       lanes open and labelled — not a slowed version of the journey. */
    if (reducedMotion) {
      if (width > 0) draw(ctx, width, height, palette, 0.97);
      return () => observer.disconnect();
    }

    let raf = 0;
    let last = 0;
    let elapsed = 0;
    let frames = 0;

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - last < FRAME_MS) return;
      elapsed += now - last;
      last = now;

      if (frames % PALETTE_EVERY === 0) palette = readPalette(canvas);
      frames += 1;

      if (width > 0) draw(ctx, width, height, palette, (elapsed % CROSSING_MS) / CROSSING_MS);
    };

    raf = requestAnimationFrame((now) => {
      last = now;
      tick(now);
    });

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="hidden h-[72px] w-full lg:block"
    />
  );
}
