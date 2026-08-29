'use client';

import { useEffect, useRef } from 'react';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { mulberry32, readChannels } from '@/lib/canvas-fx';

/**
 * The hero background, and an argument rather than an ornament.
 *
 * Four populations of points drift toward one shared attractor and none of
 * them arrives. Each group carries a permanent offset, so they orbit the same
 * answer at a fixed distance from it and from each other, forever apart. That
 * is the product: several models, one question, disagreement that is kept
 * rather than averaged into a single point.
 *
 * The obvious effect here — curl-noise particles — would have said the
 * opposite. Curl noise is divergence-free by construction: everything flows
 * together and nothing separates. Using it to depict irreducible disagreement
 * is a lie in the mathematics, so the field advects each group by its own
 * independent phase instead, and the groups never share a trajectory.
 *
 * 2D canvas, not WebGL. At this point count a shader buys nothing visible and
 * costs a context that can be lost, blocklisted, or refused, each of which
 * needs a fallback path. This always paints.
 */

/** One per generator in a Premium preset — the cross-lab floor is four. */
const GROUPS = 4;
const POINTS_PER_GROUP = 110;

/** Slow enough to read as drift rather than motion. */
const SPEED = 0.000042;
const FRAME_MS = 1000 / 30;

/** Retina buys nothing on a field of 1px dots, and costs 4x the fill. */
const MAX_DPR = 1.5;

/**
 * Both themes need most of the alpha, for opposite reasons. In dark the
 * neutral token sits close to the background and disappears into it. In light
 * it is a warm mid-grey on near-white, so every point of alpha washes it
 * toward the paper -- at 0.5 the field was there but nobody saw it.
 */
const ALPHA_LIGHT = 0.85;
const ALPHA_DARK = 0.9;

interface Point {
  readonly group: number;
  /** Position on the group's orbit, in radians. */
  readonly phase: number;
  /** Distance from the attractor, as a fraction of the shorter viewport axis. */
  readonly radius: number;
  readonly size: number;
}

function buildPoints(): readonly Point[] {
  const rand = mulberry32(0x5ea50e);
  const points: Point[] = [];

  for (let group = 0; group < GROUPS; group += 1) {
    /* Each group sits in its own annulus. The bands do not overlap, which is
       what stops the four reading as one cloud. */
    const inner = 0.16 + group * 0.085;

    for (let i = 0; i < POINTS_PER_GROUP; i += 1) {
      points.push({
        group,
        phase: rand() * Math.PI * 2,
        radius: inner + rand() * 0.07,
        size: 0.6 + rand() * 0.9,
      });
    }
  }

  return points;
}

const POINTS = buildPoints();

export function DisagreementField() {
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

    /* Read from the cascade rather than hardcoding, so the toggle, the system
       preference, and the forced-colors override all reach the canvas. */
    let neutral = '96,105,99';
    let accent = '47,56,50';
    let alpha = ALPHA_LIGHT;

    const readTheme = () => {
      neutral = readChannels(root, '--text-subtle', '#6D645F');
      accent = readChannels(root, '--accent', '#3C332E');
      alpha = root.classList.contains('dark') ? ALPHA_DARK : ALPHA_LIGHT;
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      const rect = canvas.getBoundingClientRect();

      width = rect.width;
      height = rect.height;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const paint = (time: number) => {
      context.clearRect(0, 0, width, height);

      /* The attractor: the one answer every group is reaching for. It sits
         where the headline is not, so the field never crowds the type. */
      const originX = width * 0.72;
      const originY = height * 0.46;
      const scale = Math.min(width, height);

      for (const point of POINTS) {
        /* Each group advances on its own clock. Same centre, same direction,
           permanently different position — they cannot converge. */
        const drift = time * SPEED * (1 + point.group * 0.22);
        const angle = point.phase + drift;

        /* A slow breath in the orbit radius, out of phase per group, so the
           bands flex without ever crossing. */
        const breathe = 1 + Math.sin(drift * 1.7 + point.group * 2.1) * 0.06;
        const distance = point.radius * breathe * scale;

        const x = originX + Math.cos(angle) * distance;
        const y = originY + Math.sin(angle) * distance * 0.62;

        if (x < -8 || x > width + 8 || y < -8 || y > height + 8) continue;

        /* One group in accent. Four neutral clouds read as texture; a single
           divergent colour reads as a population that disagrees. */
        const channels = point.group === 1 ? accent : neutral;
        const fade = point.group === 1 ? Math.min(1, alpha * 1.25) : alpha;

        context.fillStyle = `rgba(${channels},${fade})`;
        context.beginPath();
        context.arc(x, y, point.size, 0, Math.PI * 2);
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
      /* The whole point of the preference: one frame, then nothing. Slowing
         the loop would still be motion, and would still cost battery. */
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

    /* next-themes writes a class on <html>, so the class mutation is the one
       signal that catches both the explicit toggle and the system preference.
       matchMedia('(prefers-color-scheme)') would miss a user's own choice. */
    const themeObserver = new MutationObserver(() => {
      readTheme();
      if (reducedMotion) paint(0);
    });

    readTheme();
    resize();
    start();

    observer.observe(canvas);
    themeObserver.observe(root, { attributes: true, attributeFilter: ['class'] });
    window.addEventListener('resize', restart);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      stop();
      observer.disconnect();
      themeObserver.disconnect();
      window.removeEventListener('resize', restart);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full"
    />
  );
}
