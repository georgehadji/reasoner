'use client';

import { useEffect, useRef, useState } from 'react';
import { RUN, RUN_MODELS } from '@/lib/demo-record';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

/**
 * /how-it-works' hero fragment (data-ui): the captured run's header, and its
 * five phases as a contents list and a timing chart in one.
 *
 * Each bar is that phase's seconds against the slowest phase, so the shape is
 * a fact about this run. The bars fill in sequence at the run's own
 * proportions (compressed to ~2.2s) when first seen; reduced motion shows
 * them filled.
 */

const TOTAL_SECONDS = RUN.phases.reduce((sum, phase) => sum + phase.seconds, 0);
const MAX_SECONDS = Math.max(...RUN.phases.map((phase) => phase.seconds));

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
    <figure
      ref={ref}
      data-ui
      className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] text-[var(--site-ink)] lg:max-w-[var(--site-fragment)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
        <span className="font-semibold">One captured run</span>
        <span className="text-[var(--site-muted)] nums-tabular">{RUN.capturedOn}</span>
      </div>
      <p className="border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
        {RUN.question}
      </p>

      <nav aria-label="Phases of the run">
        <ol className="list-none">
          {RUN.phases.map((phase, i) => (
            <li key={phase.id} className="border-b border-[var(--site-line)]">
              <a
                href={`#${phase.id}`}
                className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto] items-center gap-[var(--space-3)] px-[var(--space-4)] py-[var(--space-3)] hover:bg-[var(--site-surface)]"
              >
                <span>{phase.name}</span>
                <span aria-hidden="true" className="block h-[var(--space-2)] overflow-hidden rounded-full bg-[var(--site-surface)]">
                  <span
                    className="block h-full origin-left rounded-full bg-[var(--site-accent)]"
                    style={{
                      width: `${(phase.seconds / MAX_SECONDS) * 100}%`,
                      transform: started ? 'scaleX(1)' : 'scaleX(0)',
                      transitionProperty: 'transform',
                      transitionTimingFunction: 'linear',
                      transitionDuration: reduced ? '0ms' : `${phase.seconds * TIME_SCALE}ms`,
                      transitionDelay: reduced ? '0ms' : `${OFFSETS[i] * TIME_SCALE}ms`,
                    }}
                  />
                </span>
                <span className="text-right text-[var(--site-muted)] nums-tabular">{phase.seconds.toFixed(1)}s</span>
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <figcaption className="flex flex-wrap items-center justify-between gap-[var(--space-3)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)] nums-tabular">
        <span>
          {RUN_MODELS.length} models · <code>{RUN.preset}</code>
        </span>
        <span>
          {RUN.ledger.seconds.toFixed(1)}s · ${RUN.ledger.costUsd.toFixed(4)}
        </span>
      </figcaption>
    </figure>
  );
}
