import Link from 'next/link';
import { CollagePlate, type PlateVariant } from '@/components/landing/CollagePlate';
import { PipelineRail } from '@/components/landing/PipelineRail';

/**
 * The four failures Reasoner is built against, drawn as stops on a rail.
 *
 * The section states one thing: bias, mind-virus propagation, sycophancy and
 * hallucination each get stopped, and each gets stopped somewhere different.
 * Drawing them on a rail rather than listing them is what carries the second
 * half of that claim — a list would say the four are defended, the rail says
 * where, and "where" is the part a sceptic can go and check.
 *
 * It also corrects the page's worst inherited habit: describing Reasoner as
 * though it *were* the multi-perspective pipeline. Multi-perspective is one
 * method among many and happens to be the default preset, which is exactly
 * why it kept standing in for the product. The rail is what is true of every
 * run; the method is the reasoning stage's replaceable part.
 *
 * Built from HTML and hairline borders rather than an <svg>. An SVG would
 * carry its own baked-in font sizes, breaking the page's point scale, and
 * would either shrink its labels to nothing on a phone or need a second
 * mobile drawing. Boxes on a rail reflow for free: a row on a desktop, a
 * stack on a phone, real selectable text at both.
 */

interface Stage {
  readonly href: string;
  /** Which plate is drawn above this stage. */
  readonly plate: PlateVariant;
  readonly ordinal: string;
  /** The failure mode, named. This is the line the section exists to state. */
  readonly failure: string;
  /** The stage of the run where it is actually stopped. */
  readonly stage: string;
  /** The mechanism, in one sentence, with no hedging and no adjectives. */
  readonly defence: string;
}

/**
 * Ordered by where each defence sits in a run, not by severity. A reader
 * following the rail left to right is walking the pipeline, and the four
 * failures arrive in the order the machine meets them.
 */
const STAGES: readonly Stage[] = [
  {
    href: '#bias',
    plate: 'bias',
    ordinal: '01',
    failure: 'Bias',
    stage: 'Routing',
    defence:
      'The model that writes the answer and the model that scores it never come from the same geopolitical bloc.',
  },
  {
    href: '#propagation',
    plate: 'propagation',
    ordinal: '02',
    failure: 'Mind-virus propagation',
    stage: 'Reasoning',
    defence:
      'No stage can hand an instruction to the next. Generators never read each other, and memory returns as evidence, never as an order.',
  },
  {
    // Points at the page's own §5 now that it exists, not at the run record —
    // "How it holds" should land on the argument, and /how-it-works#adjudication
    // is still there as that section's own Aside target.
    href: '#sycophancy',
    plate: 'sycophancy',
    ordinal: '03',
    failure: 'Sycophancy',
    // W2 premise audit shipped (docs/plans/sycophancy-mitigation.md) — Phase 1
    // now labels which assumptions came from the user, and the destructive
    // perspective is instructed to attack exactly those. `stage` reflects
    // where that now runs, ahead of Critique.
    stage: 'Premises',
    defence:
      'Your approval is never an input, and neither is your framing taken as settled. Phase 1 labels which assumptions came from you, a critic from another lab scores the candidates on stated criteria, and no rating you give reaches model selection.',
  },
  {
    href: '#hallucination',
    plate: 'hallucination',
    ordinal: '04',
    failure: 'Hallucination',
    stage: 'Labelling',
    defence:
      'A model’s own confidence never earns VERIFIED. With no source outside the model, the claim is downgraded in code.',
  },
];

export function MechanismDiagram() {
  return (
    <div className="mt-[var(--space-12)]">
      {/* The animated rail, desktop only — the flow is left-to-right where
          there is room for it to be, and the stages simply stack where there
          is not. See PipelineRail for why nothing in it ever merges. */}
      <PipelineRail />

      {/* Depth is applied to the row, not to each stage: one shared vanishing
          point is what makes four tilted planes read as one object seen at an
          angle rather than four cards that each warped on their own. The tilt
          is small — this is a diagram, and a stage the reader has to fight
          the perspective to read has cost more than it bought. */}
      <ol
        role="list"
        className="grid list-none gap-x-[var(--space-8)] gap-y-[var(--space-10)] [perspective:1400px] sm:grid-cols-2 lg:grid-cols-4"
      >
        {STAGES.map(({ href, plate, ordinal, failure, stage, defence }) => (
          <li
            key={href}
            className="card-hover group relative border-t border-[var(--border)] pt-[var(--space-5)] [transform-style:preserve-3d] hover:border-[var(--border-strong)] hover:[transform:translateZ(26px)_rotateX(3.5deg)] motion-reduce:hover:[transform:none]"
          >
            {/* The node on the rail. Square rather than round: the page has
                no other circles in it, and a 5px mark is the smallest that
                still reads as deliberate at this hairline weight. Below lg
                the canvas rail is gone, so this is the only node there is. */}
            <span
              aria-hidden="true"
              className="absolute -top-[3px] left-0 block h-[5px] w-[5px] bg-[var(--accent)] lg:hidden"
            />

            {/* The plate leads. It is the only part of a stage a reader
                takes in without reading, so it earns the top of the column
                and the heading answers the question it raises. */}
            <CollagePlate variant={plate} />

            <p className="nums-tabular mt-[var(--space-5)] font-mono text-[8pt] leading-[var(--lh-ui)] text-[var(--accent)]">
              {ordinal}
              <span className="ml-[var(--space-3)] font-sans font-semibold uppercase tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                {stage}
              </span>
            </p>

            {/* The failure is the headline. Naming the disease before the
                cure is the whole point of the section — a reader who does
                not recognise the problem has no use for the mechanism. */}
            <h3 className="mt-[var(--space-3)] font-serif text-[21pt] font-semibold leading-[var(--lh-subhead)] tracking-[var(--tracking-snug)] text-[var(--text)]">
              {failure}
            </h3>

            <p className="mt-[var(--space-3)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
              {defence}
            </p>

            {/* Stretched over the whole stage, but named for what it opens
                rather than read out as the entire card. */}
            <Link
              href={href}
              aria-label={`How Reasoner stops ${failure.toLowerCase()}`}
              className="link-smooth mt-[var(--space-5)] inline-flex font-sans text-[8pt] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--accent)] after:absolute after:inset-0 hover:text-[var(--accent-hover)]"
            >
              How it holds
              <span
                aria-hidden="true"
                className="ml-[var(--space-2)] inline-block transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none"
              >
                &rarr;
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
