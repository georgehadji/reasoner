'use client';

import { useEffect, useState } from 'react';
import { METHOD_PHASES } from '@/lib/config';
import { cn } from '@/lib/utils';
import { PhaseRenderer } from '@/components/phases/PhaseRenderer';
import { ResearchProgress } from '@/components/phases/ResearchProgress';
import { CHIP } from '@/components/phases/PhaseCard';
import { Tooltip } from '@/components/ui/Tooltip';
import type { RenderedPhase } from './ChatFeed';

export interface RunProgressProps {
  /** Unknown until the backend's `start` frame names it. */
  method?: string;
  /** HyperGate's reason for the method, when it chose one. */
  methodNote?: string;
  phases: RenderedPhase[];
  currentPhase?: number;
  currentPhaseName?: string;
  models?: string[];
  agents?: { name: string; task: string }[];
  researchSteps?: { step_type: string; queries: string[]; plan: string; urls: string[] }[];
  /** Epoch ms when the run was submitted. */
  startedAt?: number;
  errorPhases?: number[];
}

const PULSE =
  'animate-[skeleton-pulse_var(--dur-pulse)_var(--ease-standard)_infinite] motion-reduce:animate-none';

export function prettyMethod(method: string): string {
  return method.replace(/_/g, '-').replace(/\b\w/g, (l) => l.toUpperCase());
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/* A run while it works: one card that grows, instead of a placeholder box per
   phase. It says what is known and nothing more — "Choosing a method…" until
   the method arrives, then which step is running, how far along the plan is,
   and each finished phase as a one-line row that opens to its full output.
   When the run ends, ChatFeed swaps this for the answer (AnswerFirstRun). */
export function RunProgress({
  method,
  methodNote,
  phases,
  currentPhase,
  currentPhaseName,
  models,
  agents,
  researchSteps,
  startedAt,
  errorPhases = [],
}: RunProgressProps) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const plan = method ? (METHOD_PHASES[method.replace(/_/g, '-')] ?? []) : [];
  const doneIds = new Set(phases.map((p) => p.phase));
  const planDone = plan.filter((p) => doneIds.has(p.id)).length;
  const active = currentPhase !== undefined && !doneIds.has(currentPhase);
  const activeName = currentPhaseName || plan.find((p) => p.id === currentPhase)?.name;
  // Phases run in id order, so a plan phase below the furthest one reached was
  // skipped by the backend (e.g. classification on a fast path): drop it from
  // the count and from "Next" instead of promising it.
  const reached = [...doneIds, ...(active ? [currentPhase] : [])];
  const frontier = reached.length > 0 ? Math.max(...reached) : -Infinity;
  const upcoming = plan.filter((p) => p.id > frontier);
  const step = plan.filter((p) => doneIds.has(p.id) || (active && p.id === currentPhase)).length;
  const total = step + upcoming.length;
  // A phase running with no method named is the gate's direct or web-search
  // answer: the choice is made, so "Choosing a method…" would be stale.
  const title = method ? prettyMethod(method) : active ? 'Answering…' : 'Choosing a method…';
  const elapsed = startedAt ? formatElapsed(Math.max(0, Math.floor((now - startedAt) / 1000))) : null;

  return (
    <section
      aria-label="Run progress"
      aria-busy="true"
      className="w-full rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-4)]"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-[var(--space-3)] gap-y-[var(--space-1)]">
        <p className="m-0 text-[length:var(--text-sm)] font-semibold leading-[var(--lh-ui)] text-[var(--text)]">
          {title}
          {total > 0 && step > 0 ? (
            <span className="nums-tabular font-normal text-[var(--text-muted)]">
              {' · '}step {step} of {total}
            </span>
          ) : null}
        </p>
        {elapsed ? (
          <span className="nums-tabular font-mono text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            {elapsed}
          </span>
        ) : null}
      </div>
      {methodNote ? (
        <p className="m-0 mt-[var(--space-1)] line-clamp-2 text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
          {methodNote}
        </p>
      ) : null}

      {total > 0 ? (
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={planDone}
          aria-label={`${title}: ${planDone} of ${total} steps done`}
          className="mt-[var(--space-3)] h-[var(--space-1)] overflow-hidden rounded-[var(--radius-pill)] bg-[var(--surface-2)]"
        >
          <div
            className="h-full rounded-[var(--radius-pill)] bg-[var(--accent)] transition-[width] duration-[var(--dur-state)] ease-[var(--ease-standard)] motion-reduce:transition-none"
            style={{ width: `${(planDone / total) * 100}%` }}
          />
        </div>
      ) : null}

      <div className="mt-[var(--space-3)] flex flex-col">
        {phases.map((phase, i) => (
          <PhaseRenderer key={`${phase.phase}-${phase.index}-${i}`} phase={phase} errorPhases={errorPhases} row />
        ))}

        {active || phases.length === 0 ? (
          <div className="flex flex-col gap-[var(--space-2)] py-[var(--space-2)]">
            <div className="flex items-center gap-[var(--space-2)]">
              <span
                aria-hidden="true"
                className={cn('h-[var(--space-2)] w-[var(--space-2)] shrink-0 rounded-[var(--radius-pill)] bg-[var(--accent)]', PULSE)}
              />
              <span className="text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text)]">
                {active && activeName ? `${activeName}…` : method ? 'Starting…' : 'Reading your question…'}
              </span>
            </div>
            {active && models && models.length > 0 ? (
              <div className="flex flex-wrap gap-[var(--space-1)] pl-[var(--space-4)]">
                {models.map((m) => (
                  <span key={m} className={cn(CHIP, 'font-mono text-[length:var(--text-2xs)] text-[var(--text-subtle)]')}>
                    {m.split('/').pop() || m}
                  </span>
                ))}
              </div>
            ) : null}
            {agents && agents.length > 0 ? (
              <div className="flex flex-wrap gap-[var(--space-1)] pl-[var(--space-4)]">
                {agents.map((a) => (
                  <Tooltip key={a.name} text={a.task}>
                    <span className={cn(CHIP, 'text-[length:var(--text-2xs)] text-[var(--text-subtle)]')}>{a.name}</span>
                  </Tooltip>
                ))}
              </div>
            ) : null}
            {researchSteps && researchSteps.length > 0 ? (
              <div className="pl-[var(--space-4)]">
                <ResearchProgress steps={researchSteps} />
              </div>
            ) : null}
          </div>
        ) : null}

        {upcoming.length > 0 ? (
          <p className="m-0 pt-[var(--space-1)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
            Next: {upcoming.map((p) => p.name).join(' · ')}
          </p>
        ) : null}
      </div>
    </section>
  );
}
