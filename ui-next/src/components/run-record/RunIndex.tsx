'use client';

import { useEffect, useRef, useState } from 'react';
import { RUN } from '@/lib/demo-record';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

/**
 * The record's table of contents, and the pipeline diagram, and the only
 * timing chart on the page — one element doing all three jobs.
 *
 * Each phase's bar is as wide as its share of the run's wall clock, so the
 * shape of the strip is a fact about this run: generating four positions took
 * longer than everything except critique. The bars fill in sequence at those
 * same proportions when the strip is first seen. That is the whole animation
 * budget of the page, and it is spent on data.
 */

const TOTAL_SECONDS = RUN.phases.reduce((sum, phase) => sum + phase.seconds, 0);

/** Real seconds compressed to a watchable ~2.2s, proportions untouched. */
const TIME_SCALE = 2200 / TOTAL_SECONDS;

const OFFSETS = RUN.phases.map((_, i) =>
  RUN.phases.slice(0, i).reduce((sum, phase) => sum + phase.seconds, 0),
);

export function RunIndex() {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLElement | null>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    if (reduced || typeof IntersectionObserver === 'undefined') {
      // The IntersectionObserver capability check needs the DOM, so it cannot
      // run during render; this is the no-observer fallback path.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStarted(true);
      return;
    }
    const node = ref.current;
    if (!node) {
      setStarted(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [reduced]);

  return (
    <nav
      ref={ref}
      aria-label="Contents of the run"
      className="border-y border-[var(--border)]"
    >
      <ol
        role="list"
        className="mx-auto flex w-full max-w-[var(--width-wide)] list-none flex-col px-[var(--gutter)] sm:flex-row"
        style={{ gap: 'var(--space-4)' }}
      >
        {RUN.phases.map((phase, i) => (
          <li
            key={phase.id}
            className="min-w-0 py-[var(--space-4)]"
            /* Column width is the phase's share of the run — the strip is a
               timing chart the moment it has more than one item in a row. */
            style={{ flex: `${phase.seconds} 1 0%` }}
          >
            <a
              href={`#${phase.id}`}
              className="group block focus-visible:outline-none"
            >
              <span
                aria-hidden="true"
                className="block h-[3px] w-full overflow-hidden bg-[var(--border)]"
              >
                <span
                  className="block h-full origin-left bg-[var(--accent)]"
                  style={{
                    transform: started ? 'scaleX(1)' : 'scaleX(0)',
                    transitionProperty: 'transform',
                    transitionTimingFunction: 'linear',
                    transitionDuration: reduced ? '0ms' : `${phase.seconds * TIME_SCALE}ms`,
                    transitionDelay: reduced ? '0ms' : `${OFFSETS[i] * TIME_SCALE}ms`,
                  }}
                />
              </span>

              <span className="mt-[var(--space-3)] block font-sans text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] transition-colors duration-[var(--dur-micro)] group-hover:text-[var(--accent)]">
                {phase.name}
              </span>
              <span className="nums-tabular mt-[var(--space-1)] block font-mono text-[length:var(--text-2xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
                {phase.seconds.toFixed(1)}s
              </span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
