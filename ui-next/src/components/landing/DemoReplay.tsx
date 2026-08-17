'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import demoRun from '@/lib/demo-run.json';

/**
 * A real Reasoner run, captured 2026-08-17 by calling the production SSE
 * pipeline in-process (same code path a live request hits) and saved
 * verbatim — not a mockup. Problem asked: "Should a 12-person startup switch
 * from a monorepo to polyrepo as it scales?", preset multi-perspective-budget.
 * Regenerate with a fresh run rather than hand-editing this file.
 */
interface DemoEvent {
  type: string;
  name?: string;
  data?: {
    duration?: number;
    models?: string[];
    scores?: Array<{ perspective: string; total: number; is_top: boolean }>;
    tests?: Array<{ survival_rate: number }>;
  };
  text?: string;
}

const EVENTS = demoRun as DemoEvent[];
const PROBLEM = 'Should a 12-person startup switch from a monorepo to polyrepo as it scales?';

const PHASE_ORDER = ['Evidence Search', 'Perspectives', 'Critique & Pruning', 'Stress Testing', 'Synthesis'];

interface PhaseSummary {
  name: string;
  duration: number;
  detail: string;
}

const PHASES: PhaseSummary[] = PHASE_ORDER.map((name) => {
  const evt = EVENTS.find((e) => e.type === 'phase_complete' && e.name === name);
  const d = evt?.data;
  let detail = d?.models?.join(', ') ?? '';
  if (d?.scores) {
    const top = d.scores.find((s) => s.is_top);
    detail = `Top candidate scored ${top?.total.toFixed(1)}/10`;
  } else if (d?.tests) {
    const rate = Math.round((d.tests[0]?.survival_rate ?? 0) * 100);
    detail = `${rate}% survival under adversarial stress`;
  }
  return { name, duration: d?.duration ?? 0, detail };
});

const SYNTHESIS = EVENTS.filter((e) => e.type === 'text_chunk')
  .map((e) => e.text)
  .join(' ');

const DONE = EVENTS.find((e) => e.type === 'done') as
  | { total_tokens?: { total: number }; total_cost_usd?: number }
  | undefined;

/* Highlights [VERIFIED ...] / [HYPOTHESIS ...] / [UNKNOWN ...] spans the model
   itself emitted inline in the real output — this is what "every claim
   epistemically labeled" looks like in practice, not a UI invention. */
const LABEL_PATTERN = /\[(VERIFIED|HYPOTHESIS|UNKNOWN)([^\]]*)\]/g;
const LABEL_TONE: Record<string, string> = {
  VERIFIED: 'epistemic-verified',
  HYPOTHESIS: 'epistemic-hypothesis',
  UNKNOWN: 'epistemic-unknown',
};

function renderSynthesis(text: string) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  LABEL_PATTERN.lastIndex = 0;
  while ((match = LABEL_PATTERN.exec(text))) {
    parts.push(text.slice(last, match.index));
    parts.push(
      <span
        key={match.index}
        className={`${LABEL_TONE[match[1]]} pl-[var(--space-2)] font-sans text-[length:var(--text-xs)] font-semibold uppercase tracking-[var(--tracking-label)]`}
      >
        {match[1]}
      </span>,
    );
    last = match.index + match[0].length;
  }
  parts.push(text.slice(last));
  return parts;
}

/* `skip` bypasses the observer outright — matching LandingPage's own
   useSectionReveal: a reduced-motion visitor, or an environment where
   IntersectionObserver can't fire (no support, or a zero-size viewport),
   must never be left waiting on a signal that will never come. */
function useInView<T extends HTMLElement>(skip: boolean) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    if (skip) {
      setInView(true);
      return;
    }
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [skip]);

  return { ref, inView };
}

const STEP_INTERVAL_MS = 700;

export function DemoReplay() {
  const prefersReducedMotion = usePrefersReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>(prefersReducedMotion);
  const [step, setStep] = useState(0);
  const maxStep = PHASES.length + 1; // phases, then synthesis

  useEffect(() => {
    if (!inView) return;
    if (prefersReducedMotion) {
      setStep(maxStep);
      return;
    }
    if (step >= maxStep) return;
    const timer = setTimeout(() => setStep((s) => s + 1), STEP_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [inView, step, maxStep, prefersReducedMotion]);

  const synthesisNodes = useMemo(() => renderSynthesis(SYNTHESIS), []);
  const synthesisShown = step > PHASES.length;

  return (
    <div ref={ref} className="mx-auto w-full max-w-[var(--width-content)]">
      <p className="prose-measure mx-auto text-center font-serif text-[length:var(--text-sm)] italic leading-[var(--lh-body)] text-[var(--text-subtle)]">
        A real run — &ldquo;{PROBLEM}&rdquo;
      </p>

      <ol role="list" className="mt-[var(--space-8)] grid gap-[var(--space-3)] sm:grid-cols-5">
        {PHASES.map((phase, i) => {
          const active = step > i;
          return (
            <li
              key={phase.name}
              className={`rounded-[var(--radius)] border p-[var(--space-4)] transition-colors duration-[var(--dur-state)] ${
                active
                  ? 'border-[var(--accent-dim)] bg-[var(--surface)]'
                  : 'border-[var(--border)] bg-transparent'
              }`}
            >
              <p
                className={`font-sans text-[length:var(--text-xs)] font-semibold uppercase tracking-[var(--tracking-label)] ${
                  active ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)]'
                }`}
              >
                {phase.name}
              </p>
              <p className="mt-[var(--space-1)] font-mono text-[length:var(--text-2xs)] text-[var(--text-muted)]">
                {active ? `${phase.detail} · ${phase.duration.toFixed(1)}s` : 'Waiting…'}
              </p>
            </li>
          );
        })}
      </ol>

      <div
        className="mt-[var(--space-8)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)] transition-opacity duration-[var(--dur-component)]"
        style={{ opacity: synthesisShown ? 1 : 0 }}
      >
        {synthesisShown && (
          <>
            <p className="prose-measure whitespace-pre-wrap font-serif text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
              {synthesisNodes}
            </p>
            {DONE && (
              <p className="mt-[var(--space-6)] border-t border-[var(--border)] pt-[var(--space-4)] font-mono text-[length:var(--text-2xs)] text-[var(--text-subtle)]">
                {DONE.total_tokens?.total.toLocaleString()} tokens · $
                {DONE.total_cost_usd?.toFixed(4)} actual cost
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
