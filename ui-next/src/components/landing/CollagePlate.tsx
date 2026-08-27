/**
 * One square plate per failure mode, in the collage idiom rather than the
 * flowchart one.
 *
 * The reference is the way Anthropic illustrates an argument: a 1:1 square,
 * hard-edged flat blocks of colour cutting across each other, and one heavy
 * hand-drawn ink line laid over the top. No labels, no arrows, no legend.
 * The picture carries the feeling and the prose carries the fact.
 *
 * Where this departs from the reference on purpose: their line is a mood,
 * ours is a claim. Each of the four strokes is the failure mode drawn.
 *
 *   bias         a wave whose every turn bends the same way, so it drifts
 *                off-centre instead of oscillating around it
 *   propagation  one mark copied across the plate, each copy louder, and
 *                then cut dead by a flat block partway through
 *   sycophancy   two strokes, the second an exact mirror of the first,
 *                agreeing with it at every point
 *   hallucination a confident straight line that runs off the end of the
 *                block supporting it and keeps going over nothing
 *
 * WHAT MAKES IT READ AS INK
 * =========================
 * Studied from a 3x crop of the reference rather than guessed, because the
 * obvious guess is wrong in a specific way. At that magnification the flat
 * blocks are perfectly clean: no grain, no paper texture, no noise, a hard
 * edge at the boundary. All of the texture lives in the stroke. A paper
 * grain laid over the whole plate, which is where the instinct goes, would
 * be a departure rather than a match.
 *
 * The stroke itself does three things a plain SVG stroke cannot:
 *
 *   1. Its edges are ragged, with a fine fibrous fringe on both sides.
 *      feTurbulence into feDisplacementMap, applied to the ink only.
 *   2. Its width varies, swelling through the apex of a bend and thinning
 *      on the straights. stroke-width is constant per path, so the strokes
 *      are emitted as filled outlines instead: each sample is offset along
 *      its own normal by a width driven by the local turning angle.
 *   3. Its ends are blunt rather than round, which a filled outline gives
 *      for free and a round line cap actively prevents.
 *
 * Everything is a seeded PRNG evaluated once at module load and a fixed
 * filter seed, so the markup is deterministic. The server and the first
 * client frame cannot disagree, there is no hydration flash, and none of it
 * costs any JavaScript at runtime.
 *
 * Colours are tokens, so the plates invert along with the band they sit in.
 */

/** Plate coordinate space. Square, matching the reference's 1:1 crops. */
const SIZE = 200;

/** Straights are drawn at this fraction of the width an apex gets. */
const WIDTH_FLOOR = 0.52;

/** Samples either side to average turning angle over. */
const CURVE_SMOOTH = 6;

/** Below this, a path is straight and the curvature term is meaningless. */
const CURVE_EPS = 1e-4;

/**
 * Deterministic, so the markup is stable across renders. Same generator as
 * DisagreementField uses, for the same reason.
 */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Point {
  readonly x: number;
  readonly y: number;
}

/**
 * Walk a parametric curve and shove every sample sideways by a small random
 * amount, then thicken it into a closed outline.
 *
 * The jitter moves the centreline, which is what a hand does at the scale of
 * a whole stroke. The varying width is what a hand does at the scale of a
 * single bend: pressure rises through a turn. Doing only the first is what
 * makes a generated line still read as generated.
 */
function inkOutline(
  seed: number,
  samples: number,
  wobble: number,
  baseWidth: number,
  at: (t: number) => readonly [number, number],
): string {
  const rand = mulberry32(seed);
  const pts: Point[] = [];

  for (let i = 0; i <= samples; i += 1) {
    const t = i / samples;
    const [x, y] = at(t);
    /* Taper the wobble at both ends: a hand starts and finishes a stroke
       more precisely than it moves through the middle of one. */
    const taper = Math.sin(Math.PI * t);
    pts.push({
      x: x + (rand() - 0.5) * wobble * taper,
      y: y + (rand() - 0.5) * wobble * taper,
    });
  }

  const before = (i: number) => pts[Math.max(0, i - 1)];
  const after = (i: number) => pts[Math.min(pts.length - 1, i + 1)];

  /* Turning angle at each sample. High where the line is bending hard. */
  const turn = pts.map((p, i) => {
    const a = before(i);
    const c = after(i);
    const inbound = Math.atan2(p.y - a.y, p.x - a.x);
    const outbound = Math.atan2(c.y - p.y, c.x - p.x);
    let delta = outbound - inbound;
    while (delta > Math.PI) delta -= Math.PI * 2;
    while (delta < -Math.PI) delta += Math.PI * 2;
    return Math.abs(delta);
  });

  /* Averaged, so the width swells through a bend instead of spiking at the
     one sample that happened to carry the sharpest angle. */
  const curve = turn.map((_, i) => {
    let sum = 0;
    let n = 0;
    for (let k = -CURVE_SMOOTH; k <= CURVE_SMOOTH; k += 1) {
      const j = i + k;
      if (j >= 0 && j < turn.length) {
        sum += turn[j];
        n += 1;
      }
    }
    return sum / n;
  });

  const peak = Math.max(...curve);

  const left: string[] = [];
  const right: string[] = [];

  for (let i = 0; i < pts.length; i += 1) {
    const p = pts[i];
    const a = before(i);
    const c = after(i);

    /* Normal from the central-difference tangent. */
    const tx = c.x - a.x;
    const ty = c.y - a.y;
    const len = Math.hypot(tx, ty) || 1;
    const nx = -ty / len;
    const ny = tx / len;

    /* A straight line has no apex to swell at, so it takes full width and
       gets its life from the slow breathe term alone. */
    const bend = peak > CURVE_EPS ? curve[i] / peak : 1;
    const breathe = 0.9 + 0.1 * Math.sin((i / pts.length) * Math.PI * 3 + seed);
    const half = (baseWidth * (WIDTH_FLOOR + (1 - WIDTH_FLOOR) * bend) * breathe) / 2;

    left.push(`${(p.x + nx * half).toFixed(1)},${(p.y + ny * half).toFixed(1)}`);
    right.push(`${(p.x - nx * half).toFixed(1)},${(p.y - ny * half).toFixed(1)}`);
  }

  right.reverse();
  return `M${left.join('L')}L${right.join('L')}Z`;
}

/** A wave whose turns all bend one way, so the whole line leans as it runs. */
const BIAS_INK = inkOutline(0x1ea5, 150, 3.4, 7, (t) => [
  22 + t * 156,
  /* The mean drifts instead of holding: that is the lean. */
  46 + t * 92 + Math.sin(t * Math.PI * 3.1) * 34 * (1 - t * 0.45),
]);

/** One mark, repeated and amplified. The shape a spreading idea makes. */
const PROPAGATION_INK = [0, 1, 2, 3].map((i) =>
  inkOutline(0x51ade + i * 977, 60, 2.2 + i * 0.9, 4 + i * 1.6, (t) => [
    30 + i * 44 + Math.sin(t * Math.PI * 2) * (5 + i * 3),
    36 + t * 128,
  ]),
);

/** Two strokes that agree at every point. The second only echoes. */
const SYCOPHANCY_INK = [
  inkOutline(0x5c0f, 110, 3.0, 6.5, (t) => [30 + t * 140, 66 + Math.sin(t * Math.PI * 2.2) * 30]),
  inkOutline(0x5c10, 110, 3.0, 6.5, (t) => [30 + t * 140, 134 - Math.sin(t * Math.PI * 2.2) * 30]),
];

/** Straight, certain, and still going after its support has ended. */
const HALLUCINATION_INK = inkOutline(0xa11c, 130, 2.6, 8, (t) => [18 + t * 168, 104 - t * 8]);

export type PlateVariant = 'bias' | 'propagation' | 'sycophancy' | 'hallucination';

/**
 * Fringe settings, per variant so the four plates do not share one noise
 * field and repeat each other's edge.
 *
 * `scale` is in user units, and the plate renders 200 of them into 150px, so
 * 2.2 units is about 1.7px of displacement. That is the width of the fringe
 * in the reference at the same rendered size. Much past 3 and the stroke
 * stops reading as a mark and starts reading as a filter.
 */
const FRINGE: Record<PlateVariant, { seed: number; frequency: number; scale: number }> = {
  bias: { seed: 7, frequency: 0.65, scale: 2.2 },
  propagation: { seed: 19, frequency: 0.72, scale: 1.9 },
  sycophancy: { seed: 31, frequency: 0.68, scale: 2.1 },
  hallucination: { seed: 43, frequency: 0.6, scale: 2.4 },
};

/**
 * Flat blocks per plate. Hard rectangles only. The reference never feathers
 * an edge, and a gradient here would read as a different studio.
 *
 * These are deliberately outside the ink filter. At 3x the reference's
 * blocks carry no texture at all, and roughening them would be the one
 * change on this plate that copies the idea of the idiom rather than the
 * idiom.
 */
function Blocks({ variant }: { variant: PlateVariant }) {
  switch (variant) {
    case 'bias':
      /* A band across the middle, the reference's most-used cut. Split
         vertically as well, so the two halves sit at different weights and
         the lean has something to lean against. */
      return (
        <>
          <rect x="0" y="0" width="104" height={SIZE} fill="var(--accent)" />
          <rect x="0" y="62" width={SIZE} height="76" fill="var(--surface-3)" />
        </>
      );
    case 'propagation':
      /* The block is doing work: it lands on top of the fourth copy and
         stops it, which is the defence rather than the disease. */
      return (
        <>
          <rect x="0" y="0" width={SIZE} height={SIZE} fill="var(--surface-3)" />
          <rect x="146" y="0" width="54" height={SIZE} fill="var(--accent)" />
        </>
      );
    case 'sycophancy':
      /* Two equal halves, mirrored. The composition agrees with itself. */
      return (
        <>
          <rect x="0" y="0" width={SIZE} height="100" fill="var(--surface-3)" />
          <rect x="0" y="100" width={SIZE} height="100" fill="var(--accent)" />
        </>
      );
    case 'hallucination':
      /* Support runs out two-thirds across and the ground goes bare. */
      return (
        <>
          <rect x="0" y="0" width="132" height={SIZE} fill="var(--accent)" />
          <rect x="0" y="74" width="132" height="60" fill="var(--surface-3)" />
        </>
      );
  }
}

/**
 * Filled outlines, never strokes. Width is already baked into the path, and
 * a filled shape ends bluntly where a stroke would round itself off.
 */
function Ink({ variant }: { variant: PlateVariant }) {
  const fill = 'var(--text)';

  switch (variant) {
    case 'bias':
      return <path d={BIAS_INK} fill={fill} />;
    case 'propagation':
      return (
        <>
          {PROPAGATION_INK.map((d, i) => (
            <path key={`propagation-${i}`} d={d} fill={fill} />
          ))}
        </>
      );
    case 'sycophancy':
      return (
        <>
          {SYCOPHANCY_INK.map((d, i) => (
            <path key={`sycophancy-${i}`} d={d} fill={fill} />
          ))}
        </>
      );
    case 'hallucination':
      return <path d={HALLUCINATION_INK} fill={fill} />;
  }
}

/**
 * The plate. `aria-hidden` throughout: every one of these is a restatement
 * of the heading beneath it, and a screen reader that has just been told
 * "Hallucination" gains nothing from also being told about a line.
 */
export function CollagePlate({ variant }: { variant: PlateVariant }) {
  const fringe = FRINGE[variant];

  /* Filter ids resolve document-wide, so two plates sharing one id would
     silently both use whichever rendered first. Keyed by variant, which is
     unique across the four on the page. */
  const filterId = `plate-ink-${variant}`;

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      aria-hidden="true"
      focusable="false"
      /* Capped rather than column-width. A plate that grows to fill a
         two-column breakpoint reaches 420px and starts competing with the
         masthead; held at 150px it stays what it is, a plate beside a
         paragraph, at every width. The air left beside it in a wide column
         is the same air the reference leaves. */
      className="block aspect-square w-full max-w-[150px]"
    >
      <defs>
        {/* Generous region: the displacement pushes pixels past the path's
            own bounding box, and the default 10% would shave the fringe off
            the ends of a stroke that runs close to the plate edge. */}
        <filter id={filterId} x="-15%" y="-15%" width="130%" height="130%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency={fringe.frequency}
            numOctaves="3"
            seed={fringe.seed}
            result="fringe"
          />
          <feDisplacementMap
            in="SourceGraphic"
            in2="fringe"
            scale={fringe.scale}
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </defs>

      <Blocks variant={variant} />

      <g filter={`url(#${filterId})`}>
        <Ink variant={variant} />
      </g>

      {/*
        The third layer goes here: a greyscale photographic scrap clipped to
        one of the blocks above, which is what gives the reference plates
        their weight. It needs real assets. Put four square greyscale images
        in public/ and render them as <image clipPath="..."> between Blocks
        and the ink group. Two flat layers and a drawn line is a complete
        composition on its own, so this ships without it rather than shipping
        a fake texture.
      */}
    </svg>
  );
}
