'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Design lab for the four-card features section — see
 * `docs/plans/features-section-3d-fx-research.md`.
 *
 * Every effect here is independently toggleable so the composition can be
 * judged by eye rather than by prose. Nothing in this file is imported by the
 * app; deleting the route deletes the lab.
 *
 * Two things it exists to prove, because both are counter-intuitive:
 *  1. The inverted band cannot reuse the ambient accent — light `--accent`
 *     #96401F on #131211 measures 2.7:1. Flip `color-scheme` and let
 *     `light-dark()` hand back the opposite theme's already-measured values.
 *  2. Tilt must share `.card-hover`'s single transform chain. A second
 *     `transform` declaration silently eats the -3px lift.
 */

interface Feature {
  num: string;
  title: string;
  body: string;
  span: boolean;
  fx: 'chips' | 'planes' | 'thread' | 'counter';
}

const FEATURES: readonly Feature[] = [
  {
    num: '01',
    title: 'Verified Reasoning',
    body: 'Every claim is independently scored, cross-checked across models, and labeled VERIFIED, HYPOTHESIS, or UNKNOWN before you see it — never presented as fact without that label.',
    span: true,
    fx: 'chips',
  },
  {
    num: '02',
    title: 'Cross-Lab Consensus',
    body: 'Runs diverse models from competing labs in parallel. No single vendor bias — independent agents debate and verify every output.',
    span: false,
    fx: 'planes',
  },
  {
    num: '03',
    title: 'Grounded Research',
    body: 'Iterative web search with source verification. Every factual claim is traceable to its origin. No black-box answers.',
    span: false,
    fx: 'thread',
  },
  {
    num: '04',
    title: 'Adversarial Critique',
    body: 'Dedicated critique agents probe for logical flaws, bias, and weak evidence before final synthesis reaches you.',
    span: true,
    fx: 'counter',
  },
];

type ToggleKey = 'invert' | 'tilt' | 'spotlight' | 'beam' | 'ghost' | 'perCard' | 'elevation';

const TOGGLES: ReadonlyArray<{ key: ToggleKey; label: string; note: string }> = [
  { key: 'invert', label: 'Inverted band', note: 'color-scheme flip + light-dark()' },
  { key: 'elevation', label: 'Elevation token', note: '--card-z drives shadow + border + surface' },
  { key: 'spotlight', label: 'Container spotlight', note: 'one listener, sweeps across all four' },
  { key: 'tilt', label: 'Pointer tilt', note: 'shared perspective, max 6deg' },
  { key: 'beam', label: 'Travelling hairline', note: '@property conic border' },
  { key: 'ghost', label: 'Ghost numeral', note: 'translateZ(-40px) depth plane' },
  { key: 'perCard', label: 'Per-card FX', note: 'each effect means its own card' },
];

const MAX_TILT_DEG = 6;

export function FxLab() {
  const [on, setOn] = useState<Record<ToggleKey, boolean>>({
    invert: true,
    elevation: true,
    spotlight: true,
    tilt: true,
    beam: false,
    ghost: true,
    perCard: true,
  });

  const gridRef = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const pointer = useRef({ x: 0, y: 0 });

  const toggle = useCallback((key: ToggleKey) => {
    setOn((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  // One listener on the grid, not four. Coordinates stay container-relative so
  // the spotlight reads as a single light source crossing the whole row, which
  // is the part that actually sells depth.
  useEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    if (!on.spotlight && !on.tilt) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    // The global reduced-motion block is CSS-only with !important; a rAF loop
    // has to opt out by hand.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const paint = () => {
      frame.current = 0;
      const rect = grid.getBoundingClientRect();
      const { x, y } = pointer.current;

      if (on.spotlight) {
        grid.style.setProperty('--mx', `${((x - rect.left) / rect.width) * 100}%`);
        grid.style.setProperty('--my', `${((y - rect.top) / rect.height) * 100}%`);
      }

      if (on.tilt) {
        for (const card of Array.from(grid.querySelectorAll<HTMLElement>('[data-card]'))) {
          const box = card.getBoundingClientRect();
          const dx = (x - (box.left + box.width / 2)) / (box.width / 2);
          const dy = (y - (box.top + box.height / 2)) / (box.height / 2);
          const clamp = (n: number) => Math.max(-1, Math.min(1, n));
          card.style.setProperty('--ry', `${clamp(dx) * MAX_TILT_DEG}deg`);
          card.style.setProperty('--rx', `${clamp(-dy) * MAX_TILT_DEG}deg`);
        }
      }
    };

    const onMove = (event: PointerEvent) => {
      pointer.current = { x: event.clientX, y: event.clientY };
      if (!frame.current) frame.current = requestAnimationFrame(paint);
    };

    const onLeave = () => {
      for (const card of Array.from(grid.querySelectorAll<HTMLElement>('[data-card]'))) {
        card.style.setProperty('--rx', '0deg');
        card.style.setProperty('--ry', '0deg');
      }
    };

    grid.addEventListener('pointermove', onMove);
    grid.addEventListener('pointerleave', onLeave);
    return () => {
      grid.removeEventListener('pointermove', onMove);
      grid.removeEventListener('pointerleave', onLeave);
      if (frame.current) cancelAnimationFrame(frame.current);
      frame.current = 0;
      onLeave();
    };
  }, [on.spotlight, on.tilt]);

  return (
    <div className="min-h-dvh bg-[var(--bg)] text-[var(--text)]">
      <style>{LAB_CSS}</style>

      <header className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pt-[var(--space-10)]">
        <p className="font-mono text-[length:var(--text-xs)] uppercase tracking-[var(--tracking-label)] text-[var(--text-muted)]">
          Design lab · not linked, not indexed
        </p>
        <h1 className="mt-[var(--space-2)] font-serif text-[length:var(--text-3xl)] font-semibold leading-[var(--lh-heading)]">
          Features section — 3D &amp; FX candidates
        </h1>
        <p className="prose-measure mt-[var(--space-3)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
          Toggle each layer independently. Use the site theme switch to check the band inverts both
          ways — it takes the opposite of whatever it sits inside.{' '}
          <Link href="/" className="underline decoration-[var(--border-strong)] underline-offset-4">
            Back to home
          </Link>
        </p>

        <div className="mt-[var(--space-6)] flex flex-wrap gap-[var(--space-2)]">
          {TOGGLES.map(({ key, label, note }) => (
            <button
              key={key}
              type="button"
              onClick={() => toggle(key)}
              aria-pressed={on[key]}
              title={note}
              className="rounded-[var(--radius)] border px-[var(--space-3)] py-[var(--space-2)] font-mono text-[length:var(--text-xs)] transition-colors"
              style={{
                borderColor: on[key] ? 'var(--accent)' : 'var(--border)',
                background: on[key] ? 'var(--accent-dim)' : 'transparent',
                color: on[key] ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {on[key] ? '● ' : '○ '}
              {label}
            </button>
          ))}
        </div>
      </header>

      <section
        className="fx-band mt-[var(--space-12)] py-[var(--section-y)]"
        data-invert={on.invert ? '' : undefined}
      >
        <div
          ref={gridRef}
          className="fx-grid mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)]"
          data-spotlight={on.spotlight ? '' : undefined}
          data-tilt={on.tilt ? '' : undefined}
          data-elevation={on.elevation ? '' : undefined}
        >
          {FEATURES.map((feature) => (
            <article
              key={feature.num}
              data-card
              data-z={feature.num === '01' ? '2' : '1'}
              className={`fx-card card-hover ${feature.span ? 'fx-span-2' : ''}`}
              style={{ '--card-z': feature.num === '01' ? 2 : 1 } as React.CSSProperties}
            >
              {on.beam ? <span aria-hidden className="fx-beam" /> : null}
              {on.ghost ? (
                <span aria-hidden className="fx-ghost">
                  {feature.num}
                </span>
              ) : null}

              {on.perCard ? <CardFx fx={feature.fx} /> : null}

              <div className="fx-card-body">
                <span className="fx-num">{feature.num}</span>
                <h2 className="fx-title">{feature.title}</h2>
                <p className="fx-body">{feature.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <footer className="mx-auto w-full max-w-[var(--width-wide)] px-[var(--gutter)] pb-[var(--space-16)]">
        <p className="prose-measure font-serif text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
          Measured, not assumed: light <code className="font-mono">--accent</code> #96401F on the
          dark ground #131211 is 2.7:1 — below AA text (4.5:1) and below the 3:1 UI floor. The band
          takes #E39B80 (8.3:1) because <code className="font-mono">color-scheme</code> is flipped
          and <code className="font-mono">light-dark()</code> resolves to the other theme&apos;s
          already-measured literals. No new colours are invented anywhere on this page.
        </p>
      </footer>
    </div>
  );
}

function CardFx({ fx }: { fx: Feature['fx'] }) {
  if (fx === 'chips') {
    return (
      <div aria-hidden className="fx-chips">
        <span className="fx-chip fx-chip-verified">VERIFIED</span>
        <span className="fx-chip fx-chip-hypothesis">HYPOTHESIS</span>
        <span className="fx-chip fx-chip-unknown">UNKNOWN</span>
      </div>
    );
  }

  if (fx === 'planes') {
    return (
      <div aria-hidden className="fx-planes">
        <span className="fx-plane" style={{ '--i': 1 } as React.CSSProperties} />
        <span className="fx-plane" style={{ '--i': 2 } as React.CSSProperties} />
        <span className="fx-plane" style={{ '--i': 3 } as React.CSSProperties} />
      </div>
    );
  }

  if (fx === 'thread') {
    return (
      <svg aria-hidden className="fx-thread" viewBox="0 0 120 80" fill="none">
        <circle className="fx-thread-claim" cx="12" cy="14" r="3" />
        <path className="fx-thread-path" d="M12 14 C 12 48, 96 40, 104 68" strokeWidth="1.25" />
        <circle className="fx-thread-source" cx="104" cy="68" r="4.5" />
      </svg>
    );
  }

  return (
    <span aria-hidden className="fx-counter">
      <span className="fx-counter-plane" />
    </span>
  );
}

/**
 * Kept as one string rather than a `.css` file so the lab stays deletable in
 * one `rm -r`. Everything here is scoped under `.fx-band` / `.fx-grid` except
 * the two `[data-invert]` rules, which have to reach `:root` to know which
 * theme they are inverting away from.
 */
const LAB_CSS = `
@property --beam { syntax: '<angle>'; initial-value: 0deg; inherits: false; }

/* --- The inverted band -------------------------------------------------
   globals.css already sets the ambient color-scheme (:root 59, dark 145/197),
   so only the flip is new. Third rule covers server-rendered markup that has
   no theme class yet under a dark system preference. */
:root:not(.dark) .fx-band[data-invert]            { color-scheme: dark;  }
:root.dark       .fx-band[data-invert]            { color-scheme: light; }
@media (prefers-color-scheme: dark) {
  :root:not(.light):not(.dark) .fx-band[data-invert] { color-scheme: light; }
}

.fx-band[data-invert] {
  --bg:            light-dark(#FAF9F5, #131211);
  --surface:       light-dark(#FFFFFF, #1C1A18);
  --surface-2:     light-dark(#F1EFE7, #252220);
  --text:          light-dark(#191817, #FAF9F5);
  --text-muted:    light-dark(#6E6960, #A29C90);
  --border:        light-dark(rgb(19 18 17 / .12), rgb(250 249 245 / .11));
  --border-strong: light-dark(rgb(19 18 17 / .26), rgb(250 249 245 / .24));
  --accent:        light-dark(#96401F, #E39B80);
  --accent-dim:    light-dark(rgb(150 64 31 / .09), rgb(227 155 128 / .13));
  --ok:            light-dark(#2F6E4F, #7BC79B);
  --warn:          light-dark(#7A6012, #E8C878);
  --unknown:       light-dark(#6E6960, #A29C90);
  --red:           light-dark(#A9302B, #EF8A82);
  --shadow:        light-dark(
                     0 1px 2px rgb(19 18 17 / .05), 0 8px 24px -12px rgb(19 18 17 / .18),
                     0 1px 2px rgb(0 0 0 / .40),    0 8px 24px -12px rgb(0 0 0 / .70));
  --shadow-lg:     light-dark(
                     0 2px 4px rgb(19 18 17 / .04), 0 24px 56px -20px rgb(19 18 17 / .22),
                     0 2px 4px rgb(0 0 0 / .45),    0 24px 56px -20px rgb(0 0 0 / .80));
  background: var(--bg);
  color: var(--text);
}

/* Gotcha 4 from the research: the global prefers-contrast block hardcodes
   :root and :root.dark, so the band needs its own entry or high-contrast
   users get 11%-alpha borders on a black field. */
@media (prefers-contrast: more) {
  .fx-band[data-invert] {
    --border:        light-dark(rgb(19 18 17 / .38), rgb(250 249 245 / .38));
    --border-strong: light-dark(rgb(19 18 17 / .62), rgb(250 249 245 / .62));
  }
}

/* --- Grid --------------------------------------------------------------
   Absolute px minimum on purpose: the real section's container-query
   thresholds are absolute px, and a rem minimum overflows col-span-2 at a
   24px root font size (LandingPage.tsx comment block). */
.fx-grid {
  display: grid;
  gap: var(--space-6);
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
}
@media (min-width: 704px) {
  .fx-span-2 { grid-column: span 2; }
}
/* One vanishing point for the whole row. Without this each card tilts in its
   own space and the row reads as four unrelated toys. */
.fx-grid[data-tilt] { perspective: 1200px; }

/* --- Card --------------------------------------------------------------- */
.fx-card {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--space-8);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: transparent;
  transform-style: preserve-3d;
  /* Single chain. .card-hover owns transform; declaring it twice drops the
     -3px lift, so the lift becomes a variable instead. */
  transform:
    translateY(var(--lift, 0px))
    rotateX(var(--rx, 0deg))
    rotateY(var(--ry, 0deg));
  /* No overflow/clip-path here. Both are grouping properties: either one
     forces preserve-3d to flatten, which silently kills the ghost numeral's
     translateZ and card 02's plane stack. Anything that needs clipping does
     it in its own wrapper instead. */
}
.fx-card:hover { --lift: -3px; }
.fx-card.card-hover:hover { transform:
  translateY(var(--lift, 0px)) rotateX(var(--rx, 0deg)) rotateY(var(--ry, 0deg)); }

/* Elevation as a token: shadow, border alpha and surface all read from
   --card-z, so a "raised" card is raised in three ways at once. */
.fx-grid[data-elevation] .fx-card {
  background: color-mix(in oklab, var(--surface) calc(var(--card-z, 0) * 45%), transparent);
  box-shadow: var(--shadow);
}
.fx-grid[data-elevation] .fx-card[data-z="2"] {
  background: var(--surface);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-lg);
}

/* Spotlight. Container-relative coordinates, so one gradient origin crosses
   all four cards as a single light source. */
.fx-grid[data-spotlight] .fx-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: radial-gradient(
    240px circle at var(--mx, 50%) var(--my, 50%),
    var(--accent-dim),
    transparent 60%
  );
  opacity: 0;
  transition: opacity var(--dur-state) var(--ease-standard);
}
@media (hover: hover) and (pointer: fine) {
  .fx-grid[data-spotlight]:hover .fx-card::before { opacity: 1; }
}

.fx-card-body { position: relative; display: flex; flex-direction: column; height: 100%; }
.fx-num {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  letter-spacing: var(--tracking-label);
  color: var(--accent);
}
.fx-title {
  margin-top: var(--space-3);
  font-family: var(--font-serif);
  font-size: var(--text-xl);
  font-weight: 600;
  line-height: var(--lh-heading);
  color: var(--text);
}
.fx-body {
  margin-top: var(--space-3);
  max-width: 46ch;
  font-family: var(--font-serif);
  font-size: var(--text-sm);
  line-height: var(--lh-body);
  color: var(--text-muted);
}

/* Ghost numeral — one element, no JS, gives the card a literal background
   plane to sit in front of. */
.fx-ghost {
  position: absolute;
  top: var(--space-2);
  right: var(--space-4);
  font-family: var(--font-mono);
  font-size: clamp(5rem, 12vw, 9rem);
  font-weight: 700;
  line-height: 1;
  color: color-mix(in oklab, var(--text) 6%, transparent);
  transform: translateZ(-40px);
  pointer-events: none;
  user-select: none;
}

/* Travelling hairline. @property typing is what makes the angle animatable;
   where registered-property animation is unsupported the gradient renders
   static, which is still a perfectly good border. */
.fx-beam {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: conic-gradient(from var(--beam), transparent 0 82%, var(--accent) 92%, transparent 100%);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  mask-composite: exclude;
  pointer-events: none;
}
@media (prefers-reduced-motion: no-preference) {
  .fx-beam { animation: fx-beam-spin 6s linear infinite; }
}
@keyframes fx-beam-spin { to { --beam: 360deg; } }

/* --- 01 · epistemic chips ---------------------------------------------
   Reuses the product's own vocabulary rather than inventing decoration:
   solid / dashed / dotted 3px left borders, same as globals.css:981. */
.fx-chips {
  position: absolute;
  right: var(--space-8);
  bottom: var(--space-8);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
  pointer-events: none;
}
.fx-chip {
  padding: 2px var(--space-2);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: var(--tracking-label);
  background: var(--surface-2);
  opacity: 0;
  transform: translateX(8px);
}
@media (prefers-reduced-motion: no-preference) {
  .fx-chip { animation: fx-chip-in var(--dur-component) var(--ease-entrance) forwards; }
  .fx-chip-hypothesis { animation-delay: 140ms; }
  .fx-chip-unknown    { animation-delay: 280ms; }
}
@media (prefers-reduced-motion: reduce) {
  .fx-chip { opacity: 1; transform: none; }
}
@keyframes fx-chip-in { to { opacity: 1; transform: translateX(0); } }
.fx-chip-verified   { border-left: 3px solid var(--ok);      color: var(--ok); }
.fx-chip-hypothesis { border-left: 3px dashed var(--warn);   color: var(--warn); }
.fx-chip-unknown    { border-left: 3px dotted var(--unknown); color: var(--unknown); }

/* --- 02 · parallel planes ---------------------------------------------- */
.fx-planes {
  position: absolute;
  inset: var(--space-6);
  transform-style: preserve-3d;
  pointer-events: none;
}
.fx-plane {
  position: absolute;
  inset: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transform:
    translateZ(calc(var(--i) * -22px))
    translateX(calc(var(--i) * 6px))
    rotateZ(calc(var(--i) * 0.6deg));
  opacity: calc(0.5 / var(--i));
  transition: transform var(--dur-component) var(--ease-entrance),
              opacity var(--dur-component) var(--ease-standard);
}
.fx-card:hover .fx-plane {
  transform: translateZ(calc(var(--i) * -6px)) translateX(0) rotateZ(0deg);
  opacity: calc(0.8 / var(--i));
}

/* --- 03 · citation thread ---------------------------------------------- */
.fx-thread {
  position: absolute;
  right: var(--space-6);
  bottom: var(--space-6);
  width: 120px;
  height: 80px;
  pointer-events: none;
}
.fx-thread-claim  { fill: var(--accent); }
/* Recession by opacity, not translateZ: SVG has no 3D coordinate system, so
   a translateZ on a child element is simply dropped. Putting the source on a
   real plane behind the claim needs two HTML elements, not two SVG nodes. */
.fx-thread-source { fill: none; stroke: var(--accent); stroke-width: 1.25; opacity: 0.55; }
.fx-thread-path   { stroke: var(--border-strong); stroke-dasharray: 160; stroke-dashoffset: 160; }
@media (prefers-reduced-motion: no-preference) {
  .fx-thread-path { animation: fx-thread-draw 1.6s var(--ease-entrance) forwards; }
}
@media (prefers-reduced-motion: reduce) {
  .fx-thread-path { stroke-dashoffset: 0; }
}
@keyframes fx-thread-draw { to { stroke-dashoffset: 0; } }

/* --- 04 · rejected counter-plane ---------------------------------------
   The only card allowed the red token. It arrives, is refused, retreats. */
.fx-counter {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  /* This one DOES clip — the plane enters from off-card. So it cannot carry
     preserve-3d (overflow would flatten it anyway); it brings its own
     perspective so the child's rotateY still reads as depth. */
  overflow: hidden;
  perspective: 800px;
  pointer-events: none;
}
.fx-counter-plane {
  position: absolute;
  inset: 12% 0;
  border-left: 2px solid var(--red);
  background: linear-gradient(90deg, color-mix(in oklab, var(--red) 12%, transparent), transparent);
  transform: translateX(-105%) rotateY(14deg);
  opacity: 0;
}
@media (prefers-reduced-motion: no-preference) {
  .fx-card:hover .fx-counter-plane {
    animation: fx-counter-reject 1.8s var(--ease-standard);
  }
}
@keyframes fx-counter-reject {
  0%   { transform: translateX(-105%) rotateY(14deg); opacity: 0; }
  35%  { transform: translateX(10%)   rotateY(6deg);  opacity: 1; }
  55%  { transform: translateX(22%)   rotateY(6deg);  opacity: 1; }
  100% { transform: translateX(-105%) rotateY(14deg); opacity: 0; }
}
`;
