import {
  CODE_CONTRACT,
  CODE_SHOWCASE_FILE,
  CODE_SHOWCASE_FINDINGS,
  CODE_SHOWCASE_REQUEST,
  CODE_SHOWCASE_VERDICT,
} from '@/lib/code-showcase';

/**
 * The coding section's exhibit: one generated file, and the adversarial
 * review a second model from a second lab hands back on it.
 *
 * The section's claim is a handoff, so the drawing is a handoff. Two plates,
 * the review overhanging the code it is about, which is the one arrangement
 * that says "this came after that and is about it" without a caption saying so.
 *
 * DEPTH. The page owns exactly one depth language and this borrows it rather
 * than inventing a second: `[perspective:1400px]` on the container so both
 * plates share a vanishing point, and the canonical
 * `translateZ(26px) rotateX(3.5deg)` on hover — the same numbers as
 * MechanismDiagram and the image grid. Nothing here adds a keyframe or a
 * class to globals.css, so there is also nothing new for the
 * prefers-reduced-motion block to have to opt out by name (the two
 * scroll-driven animations already there had to be, see globals.css:1211).
 *
 * At rest the plates stay flat and the depth is carried by overlap, a real
 * shadow and the accent light above — not by rotation. MechanismDiagram's
 * rule is that a stage the reader has to fight the perspective to read has
 * cost more than it bought, and that goes double for a code listing: rotated
 * monospace is the one thing on this page nobody would forgive.
 *
 * COLOUR. CRITICAL is --red. --ok / --warn / --unknown are not touched:
 * those three tokens carry VERIFIED / HYPOTHESIS / UNKNOWN and nothing else
 * (globals.css:107-115), and borrowing them for a severity tier would put a
 * second meaning on the page's most load-bearing colours.
 *
 * See lib/code-showcase.ts for what this is and is not allowed to claim.
 */

/** Only CRITICAL earns a colour. The rest are ranked by weight alone. */
const SEVERITY_CLASS: Record<string, string> = {
  CRITICAL: 'text-[var(--red)]',
  HIGH: 'text-[var(--text)]',
  MEDIUM: 'text-[var(--text-muted)]',
};

export function ReviewHandoff() {
  return (
    <figure className="relative mt-[var(--space-10)]">
      {/* The light the plates are lit by. Same static gradient on the same
          token as the image grid — no canvas, no loop, nothing to pause when
          it scrolls out of view. Painted first and never given a z-index: the
          plates are opaque and come later in the DOM, so they cover it
          without a stacking context having to be invented here. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-[-8%] top-[4%] h-[55%] bg-[radial-gradient(ellipse_at_top,var(--accent-dim),transparent_70%)]"
      />

      <p className="relative font-mono text-[13pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
        &ldquo;{CODE_SHOWCASE_REQUEST}&rdquo;
      </p>

      {/* The code column is the wider of the two: it holds a fixed-width
          listing that must not need a scrollbar, whereas the findings
          reflow to whatever they are given. gap-0 because the overlap
          below IS the gap. */}
      <div className="relative mt-[var(--space-6)] grid items-start gap-[var(--space-6)] [perspective:1400px] lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-0">
        {/* ── The file, as written ───────────────────────────── */}
        <div className="plate-reveal card-hover group border border-[var(--border)] bg-[var(--surface)] [transform-style:preserve-3d] hover:border-[var(--border-strong)] hover:[transform:translateZ(26px)_rotateX(3.5deg)] motion-reduce:hover:[transform:none]">
          <div className="flex items-baseline justify-between gap-[var(--space-4)] border-b border-[var(--border)] px-[var(--space-5)] py-[var(--space-3)]">
            <p className="font-mono text-[8pt] leading-[var(--lh-ui)] text-[var(--text-2)]">
              {CODE_SHOWCASE_FILE.path}
            </p>
            <p className="font-sans text-[8pt] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
              Written
            </p>
          </div>

          {/* The scroller is INSIDE the plate, never on it. overflow on the
              transformed element forces transform-style back to flat and
              kills the tilt for the whole column. */}
          <pre className="overflow-x-auto px-[var(--space-5)] py-[var(--space-4)]">
            <code className="block font-mono text-[13pt] leading-[1.7]">
              {CODE_SHOWCASE_FILE.lines.map(({ n, text, flagged }) => (
                <span key={n} className="flex gap-[var(--space-4)]">
                  {/* The gutter says which lines the review came back on,
                      so the two plates can be read against each other
                      without counting rows. */}
                  <span
                    aria-hidden="true"
                    className={`nums-tabular w-[1.5em] shrink-0 text-right text-[8pt] ${
                      flagged ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)]'
                    }`}
                  >
                    {n}
                  </span>
                  <span
                    className={
                      flagged
                        ? 'whitespace-pre text-[var(--text)]'
                        : 'whitespace-pre text-[var(--text-muted)]'
                    }
                  >
                    {text}
                  </span>
                </span>
              ))}
            </code>
          </pre>
        </div>

        {/* ── The review that came back ──────────────────────────
            Overhangs the code plate from lg up, and is dropped down the
            page a little. Overlap is the whole drawing: it is what makes
            the review read as a thing laid on top of the file rather than
            as a second panel sitting beside it. z-10 because the negative
            margin puts it over a sibling that is opaque. */}
        <div className="plate-reveal card-hover group relative z-10 border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-lg)] [transform-style:preserve-3d] hover:border-[var(--border-strong)] hover:[transform:translateZ(26px)_rotateX(3.5deg)] motion-reduce:hover:[transform:none] lg:-ml-[var(--space-10)] lg:mt-[var(--space-12)]">
          <div className="flex items-baseline justify-between gap-[var(--space-4)] border-b border-[var(--border)] px-[var(--space-5)] py-[var(--space-3)]">
            <p className="font-sans text-[8pt] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
              Reviewed &mdash; different model, different lab
            </p>
            <p className="nums-tabular font-mono text-[8pt] leading-[var(--lh-ui)] text-[var(--red)]">
              {CODE_SHOWCASE_VERDICT}
            </p>
          </div>

          <ul role="list" className="list-none px-[var(--space-5)] py-[var(--space-2)]">
            {CODE_SHOWCASE_FINDINGS.map(({ severity, line, issue, fix }) => (
              <li
                key={`${severity}-${line}`}
                className="border-b border-[var(--border)] py-[var(--space-4)] last:border-b-0"
              >
                <p className="nums-tabular font-mono text-[8pt] leading-[var(--lh-ui)]">
                  <span className={`font-semibold ${SEVERITY_CLASS[severity]}`}>{severity}</span>
                  <span className="ml-[var(--space-3)] text-[var(--text-subtle)]">
                    {CODE_SHOWCASE_FILE.path}:{line}
                  </span>
                </p>
                <p className="mt-[var(--space-2)] font-serif text-[13pt] leading-[var(--lh-body)] text-[var(--text-2)]">
                  {issue}
                </p>
                {fix ? (
                  <p className="mt-[var(--space-1)] font-mono text-[8pt] leading-[var(--lh-body)] text-[var(--text-muted)]">
                    {fix}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Says plainly what this is. The image grid above it is a real run and
          this is not, and a page that spends its credibility arguing for
          checkable claims cannot let a reader assume otherwise. */}
      <figcaption className="relative mt-[var(--space-6)] font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-muted)]">
        The fields every review returns, on a file small enough to check by eye. Seven phases run
        in all: library research, spec, generation, CVE search, security review, tests, assembly.
      </figcaption>

      {/* ── The contract ──────────────────────────────────────────
          Last, because it is the answer to the question the review raises:
          if a reviewer is finding this, what was the writer aiming at? Eight
          clauses, appended to the generation prompt and the test prompt
          alike. Two columns rather than one — these are unordered peers, not
          a sequence, and stacking eight of them would borrow the writing
          section's shape for content that has no order in it. */}
      <ul
        role="list"
        className="mt-[var(--space-10)] grid list-none gap-x-[var(--space-8)] gap-y-[var(--space-3)] sm:grid-cols-2"
      >
        {CODE_CONTRACT.map((clause) => (
          <li
            key={clause}
            className="border-t border-[var(--border)] pt-[var(--space-3)] font-sans text-[13pt] leading-[var(--lh-ui)] text-[var(--text-2)]"
          >
            {clause}
          </li>
        ))}
      </ul>
    </figure>
  );
}
