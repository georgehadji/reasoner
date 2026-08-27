'use client';

import { useEffect, useRef } from 'react';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { mulberry32, readChannels } from '@/lib/canvas-fx';

/**
 * The Ideation section's exhibit, and the complement of the hero field.
 *
 * DisagreementField is points converging on a centre they permanently miss.
 * This is the opposite motion: points radiating outward from one shared
 * origin — the prompt — and never returning to it. Most settle close in,
 * because a model's most probable answers cluster near its own reflex. A
 * distinguished few reach far out, tied back to the origin by a thin line,
 * because those are the ones that got pulled out and taken further: exactly
 * `DEVELOPED`, the same count the pipeline actually develops
 * (application/flows/brainstorming_phases.py). The dl beside this carries the
 * words; this carries the shape, so a reader who never reads a caption still
 * sees the claim — most of what comes back is safe, and the one that matters
 * is the one that almost stayed home.
 *
 * 2D canvas, matching the hero field, for the same reason: nothing here needs
 * a shader, and a shader is a context that can be lost or refused.
 */

/** Density matched to the hero field (~3×10⁻⁴ points/px²), scaled to a much smaller box. */
const TOTAL_POINTS = 64;

/** Ideas that reach deep development, by default — everything else stops at the merge. */
const DEVELOPED = 3;

const FRAME_MS = 1000 / 30;
const MAX_DPR = 1.5;
const ALPHA_LIGHT = 0.8;
const ALPHA_DARK = 0.85;
const LINE_ALPHA = 0.3;

interface Idea {
  readonly angle: number;
  /** Resting distance from the origin, as a fraction of the box's half-axis. */
  readonly radius: number;
  readonly size: number;
  readonly wobblePhase: number;
  readonly developed: boolean;
}

/**
 * Deterministic, so SSR markup and the first client frame cannot disagree.
 * `radius` is drawn with a bias toward the origin — `rand() ** 2.4` puts the
 * median draw at a fifth of the way out and only a rare tail near the edge —
 * because that lopsided shape is the actual claim: most of a model's output
 * is close to its reflex, and reach is the exception. The `DEVELOPED` ideas
 * that farthest reached are the ones marked and linked back to the origin.
 */
function buildIdeas(): readonly Idea[] {
  const rand = mulberry32(0x1dea);
  const raw: Idea[] = [];

  for (let i = 0; i < TOTAL_POINTS; i += 1) {
    raw.push({
      angle: rand() * Math.PI * 2,
      radius: rand() ** 2.4,
      size: 1.1 + rand() * 1,
      wobblePhase: rand() * Math.PI * 2,
      developed: false,
    });
  }

  const farthest = [...raw].sort((a, b) => b.radius - a.radius).slice(0, DEVELOPED);
  const developedSet = new Set(farthest);
  return raw.map((idea) => (developedSet.has(idea) ? { ...idea, developed: true } : idea));
}

const IDEAS = buildIdeas();

export function IdeaField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const context = canvas.getContext('2d');
    if (!context) return;

    const root = document.documentElement;
    let width = 0;
    let height = 0;
    let frame = 0;
    let lastPaint = 0;
    let visible = true;

    let neutral = '110,105,96';
    let accent = '150,64,31';
    let strong = '38,35,31';
    let alpha = ALPHA_LIGHT;

    const readTheme = () => {
      neutral = readChannels(root, '--text-subtle', '#6E6960');
      accent = readChannels(root, '--accent', '#96401F');
      strong = readChannels(root, '--text', '#26231F');
      alpha = root.classList.contains('dark') ? ALPHA_DARK : ALPHA_LIGHT;
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;

      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const paint = (time: number) => {
      if (width === 0 || height === 0) return;
      context.clearRect(0, 0, width, height);

      const originX = width * 0.5;
      const originY = height * 0.52;
      const scaleX = width * 0.46;
      const scaleY = height * 0.4;

      /* A slow breath around each idea's resting radius, out of phase per
         point, so the field stays alive without any point ever travelling —
         nothing here is "in transit," everything has already landed. */
      const position = (idea: Idea) => {
        const breathe = 1 + Math.sin(time * 0.0009 + idea.wobblePhase) * 0.05;
        const r = idea.radius * breathe;
        return {
          x: originX + Math.cos(idea.angle) * r * scaleX,
          y: originY + Math.sin(idea.angle) * r * scaleY,
        };
      };

      /* Reach lines under the dots, only for the ones that got developed. */
      context.lineWidth = 1;
      context.strokeStyle = `rgba(${accent},${LINE_ALPHA})`;
      for (const idea of IDEAS) {
        if (!idea.developed) continue;
        const { x, y } = position(idea);
        context.beginPath();
        context.moveTo(originX, originY);
        context.lineTo(x, y);
        context.stroke();
      }

      /* The origin: the one fixed thing, the prompt everything else answers. */
      context.fillStyle = `rgba(${strong},1)`;
      context.beginPath();
      context.arc(originX, originY, 2.6, 0, Math.PI * 2);
      context.fill();

      /* Two passes, not one interleaved: only three of these are developed,
         but array order does not know that, and a neutral dot drawn after an
         accent one would paint over it. Neutral first, developed always
         last, so the three that matter are never buried under the crowd. */
      context.fillStyle = `rgba(${neutral},${alpha})`;
      for (const idea of IDEAS) {
        if (idea.developed) continue;
        const { x, y } = position(idea);
        context.beginPath();
        context.arc(x, y, idea.size, 0, Math.PI * 2);
        context.fill();
      }

      for (const idea of IDEAS) {
        if (!idea.developed) continue;
        const { x, y } = position(idea);
        const pulse = 0.65 + Math.sin(time * 0.0006 + idea.wobblePhase * 1.3) * 0.35;
        context.fillStyle = `rgba(${accent},${pulse})`;
        context.beginPath();
        context.arc(x, y, idea.size * 1.7, 0, Math.PI * 2);
        context.fill();
      }
    };

    const loop = (time: number) => {
      frame = window.requestAnimationFrame(loop);
      if (time - lastPaint < FRAME_MS) return;
      lastPaint = time;
      paint(time);
    };

    const stop = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = 0;
    };

    const start = () => {
      stop();
      /* One frame, then nothing — a slowed loop is still motion and still
         costs battery. */
      if (reducedMotion) {
        paint(0);
        return;
      }
      frame = window.requestAnimationFrame(loop);
    };

    const restart = () => {
      readTheme();
      resize();
      start();
    };

    /* Paused off-screen and in a backgrounded tab, same as the hero field. */
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

    const themeObserver = new MutationObserver(() => {
      readTheme();
      if (reducedMotion) paint(0);
    });

    readTheme();
    resize();
    start();

    observer.observe(canvas);
    themeObserver.observe(root, { attributes: true, attributeFilter: ['class'] });
    const resizeObserver = new ResizeObserver(restart);
    resizeObserver.observe(canvas);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      observer.disconnect();
      themeObserver.disconnect();
      resizeObserver.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none mt-[var(--space-8)] block h-[180px] w-full sm:h-[220px]"
    />
  );
}
