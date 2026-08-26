/**
 * One square plate per failure mode, in the collage idiom rather than the
 * flowchart one.
 *
 * The reference is the way Anthropic illustrates an argument: a 1:1 square,
 * hard-edged flat blocks of colour cutting across each other, and one heavy
 * hand-drawn ink line laid over the top. No labels, no arrows, no legend —
 * the picture carries the feeling and the prose carries the fact. Their
 * plates add a third layer, a greyscale photographic scrap (marbled paper,
 * a stone, an old survey map). We have two of the three; see the note at the
 * bottom of this file for the slot the third one goes in.
 *
 * Where this departs from the reference on purpose: their line is a mood,
 * ours is a claim. Each of the four strokes is the failure mode drawn —
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
 * Server-rendered SVG, not canvas. The jitter that makes a stroke read as
 * ink rather than as a bezier comes from a seeded PRNG evaluated once at
 * module load, so the markup is deterministic — the server and the first
 * client frame cannot disagree, there is no hydration flash, and the whole
 * thing costs no JavaScript at runtime.
 *
 * Colours are tokens, so the plates invert along with the band they sit in.
 */

/** Plate coordinate space. Square, matching the reference's 1:1 crops. */
const SIZE = 200;

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

/**
 * Walk a parametric curve and shove every sample sideways by a small random
 * amount. A clean bezier reads as software; a line that wobbles by a couple
 * of units and never quite closes the same way twice reads as a hand.
 */
function inkPath(
  seed: number,
  samples: number,
  wobble: number,
  at: (t: number) => readonly [number, number],
): string {
  const rand = mulberry32(seed);
  const points: string[] = [];

  for (let i = 0; i <= samples; i += 1) {
    const t = i / samples;
    const [x, y] = at(t);
    /* Taper the wobble at both ends: a hand starts and finishes a stroke
       more precisely than it moves through the middle of one. */
    const taper = Math.sin(Math.PI * t);
    const dx = (rand() - 0.5) * wobble * taper;
    const dy = (rand() - 0.5) * wobble * taper;
    points.push(`${(x + dx).toFixed(1)},${(y + dy).toFixed(1)}`);
  }

  return `M${points.join('L')}`;
}

/** A wave whose turns all bend one way, so the whole line leans as it runs. */
const BIAS_LINE = inkPath(0x1ea5, 150, 3.4, (t) => [
  22 + t * 156,
  /* The mean drifts instead of holding: that is the lean. */
  46 + t * 92 + Math.sin(t * Math.PI * 3.1) * 34 * (1 - t * 0.45),
]);

/** One mark, repeated and amplified — the shape a spreading idea makes. */
const PROPAGATION_LINES = [0, 1, 2, 3].map((i) =>
  inkPath(0x51ade + i * 977, 60, 2.2 + i * 0.9, (t) => [
    30 + i * 44 + Math.sin(t * Math.PI * 2) * (5 + i * 3),
    36 + t * 128,
  ]),
);

/** Two strokes that agree at every point. The second only echoes. */
const SYCOPHANCY_LINES = [
  inkPath(0x5c0f, 110, 3.0, (t) => [30 + t * 140, 66 + Math.sin(t * Math.PI * 2.2) * 30]),
  inkPath(0x5c10, 110, 3.0, (t) => [30 + t * 140, 134 - Math.sin(t * Math.PI * 2.2) * 30]),
];

/** Straight, certain, and still going after its support has ended. */
const HALLUCINATION_LINE = inkPath(0xa11c, 130, 2.6, (t) => [18 + t * 168, 104 - t * 8]);

export type PlateVariant = 'bias' | 'propagation' | 'sycophancy' | 'hallucination';

/**
 * Flat blocks per plate. Hard rectangles only — the reference never feathers
 * an edge, and a gradient here would read as a different studio.
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
      /* Two equal halves, mirrored — the composition agrees with itself. */
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

function Ink({ variant }: { variant: PlateVariant }) {
  const stroke = {
    stroke: 'var(--text)',
    fill: 'none',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };

  switch (variant) {
    case 'bias':
      return <path d={BIAS_LINE} strokeWidth="7" {...stroke} />;
    case 'propagation':
      return (
        <>
          {PROPAGATION_LINES.map((d, i) => (
            <path key={d.slice(0, 12) + i} d={d} strokeWidth={4 + i * 1.6} {...stroke} />
          ))}
        </>
      );
    case 'sycophancy':
      return (
        <>
          {SYCOPHANCY_LINES.map((d) => (
            <path key={d.slice(0, 12)} d={d} strokeWidth="6.5" {...stroke} />
          ))}
        </>
      );
    case 'hallucination':
      return <path d={HALLUCINATION_LINE} strokeWidth="8" {...stroke} />;
  }
}

/**
 * The plate. `aria-hidden` throughout: every one of these is a restatement
 * of the heading beneath it, and a screen reader that has just been told
 * "Hallucination" gains nothing from also being told about a line.
 */
export function CollagePlate({ variant }: { variant: PlateVariant }) {
  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      aria-hidden="true"
      focusable="false"
      /* Capped rather than column-width. A plate that grows to fill a
         two-column breakpoint reaches 420px and starts competing with the
         masthead; held at 220px it stays what it is — a plate beside a
         paragraph — at every width, and the air left beside it in a wide
         column is the same air the reference leaves. */
      className="block aspect-square w-full max-w-[220px]"
    >
      <Blocks variant={variant} />
      <Ink variant={variant} />
      {/*
        The third layer goes here: a greyscale photographic scrap clipped to
        one of the blocks above, which is what gives the reference plates
        their weight. It needs real assets — put four square greyscale images
        in public/ and render them as <image clipPath="…"> between Blocks and
        Ink. Two flat layers and a drawn line is a complete composition on its
        own, so this ships without it rather than shipping a fake texture.
      */}
    </svg>
  );
}
