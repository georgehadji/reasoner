'use client';

import React, { useMemo } from 'react';
import { METHOD_PHASES } from '@/lib/config';
import { cn } from '@/lib/utils';

interface PhaseTimelineProps {
  method: string;
  currentPhase?: number;
  completedPhases: number[];
  errorPhases?: number[];
  phaseDurations?: Record<number, number>;
  onPhaseClick?: (phaseId: number) => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
}

function PhaseTimelineComponent({
  method,
  currentPhase,
  completedPhases,
  errorPhases = [],
  phaseDurations,
  onPhaseClick,
  onExpandAll,
  onCollapseAll,
}: PhaseTimelineProps) {
  const normalized = method.replace(/_/g, '-');
  const phases = useMemo(() => METHOD_PHASES[normalized] || METHOD_PHASES['multi-perspective'], [normalized]);
  const statusMap = useMemo(() => {
    const map = new Map<number, 'pending' | 'active' | 'completed' | 'error'>();
    phases.forEach((p) => {
      if (errorPhases.includes(p.id)) map.set(p.id, 'error');
      else if (currentPhase === p.id) map.set(p.id, 'active');
      else if (completedPhases.includes(p.id)) map.set(p.id, 'completed');
      else map.set(p.id, 'pending');
    });
    return map;
  }, [phases, currentPhase, completedPhases, errorPhases]);

  return (
    <nav
      aria-label="Pipeline phases"
      aria-live="polite"
      className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--bg)]/90 px-4 py-2 backdrop-blur-sm"
    >
      <div className="relative flex flex-1 items-center gap-1.5 overflow-x-auto scrollbar-thin pb-px">
        {/* Fade gradient indicating more content on the right */}
        <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-[var(--bg)] to-transparent z-10" />
        {phases.map((p) => {
          const isCompleted = completedPhases.includes(p.id);
          const isActive = currentPhase === p.id;
          const isError = errorPhases.includes(p.id);

          return (
            <button
              key={p.id}
              type="button"
              disabled={!isCompleted}
              onClick={() => onPhaseClick?.(p.id)}
              aria-label={`${p.name} \u2014 ${isActive ? 'In progress' : isError ? 'Error' : isCompleted ? 'Completed' : 'Pending'}`}
              className={cn(
                'flex shrink-0 cursor-pointer items-center gap-1.5 rounded-[var(--radius)] px-3 py-2.5 text-left',
                'transition-all duration-300 ease-out',
                isActive
                  ? 'bg-[var(--accent-dim)] text-[var(--text)]'
                  : isCompleted
                    ? 'cursor-pointer text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]'
                    : 'cursor-default text-[var(--text-subtle)] opacity-50',
              )}
            >
              {/* Dot indicator with smooth state transitions */}
              <span className="relative flex h-2 w-2 shrink-0 items-center justify-center">
                <span
                  className={cn(
                    'h-2 w-2 rounded-full transition-all duration-500',
                    isError
                      ? 'bg-[var(--red)]'
                      : isActive
                        ? 'bg-[var(--accent)] scale-110'
                        : isCompleted
                          ? 'bg-[var(--text-muted)]'
                          : 'bg-[var(--surface-3)]',
                  )}
                />
                {isActive && (
                  <span
                    className="absolute inline-flex h-full w-full rounded-full bg-[var(--accent)] motion-reduce:animate-none"
                    style={{
                      animation: 'phase-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite',
                    }}
                  />
                )}
              </span>

              {/* Label */}
              <span className="text-[length:var(--text-xs)] transition-colors duration-300">
                {p.short}
                {isCompleted && phaseDurations?.[p.id] !== undefined && (
                  <span className="ml-1 opacity-50 tabular-nums">{phaseDurations[p.id].toFixed(1)}s</span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      {(onExpandAll || onCollapseAll) && (
        <div className="flex shrink-0 items-center gap-1.5">
          {onExpandAll && (
            <button
              type="button"
              onClick={onExpandAll}
              className="cursor-pointer rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-[length:var(--text-2xs)] font-medium text-[var(--text-muted)] transition-all duration-200 hover:border-[var(--border-strong)] hover:text-[var(--text)]"
            >
              Expand all
            </button>
          )}
          {onCollapseAll && (
            <button
              type="button"
              onClick={onCollapseAll}
              className="cursor-pointer rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-[length:var(--text-2xs)] font-medium text-[var(--text-muted)] transition-all duration-200 hover:border-[var(--border-strong)] hover:text-[var(--text)]"
            >
              Collapse all
            </button>
          )}
        </div>
      )}
    </nav>
  );
}

export const PhaseTimeline = React.memo(PhaseTimelineComponent, (prev, next) => {
  return (
    prev.method === next.method &&
    prev.currentPhase === next.currentPhase &&
    prev.completedPhases.length === next.completedPhases.length &&
    prev.errorPhases?.length === next.errorPhases?.length &&
    JSON.stringify(prev.phaseDurations) === JSON.stringify(next.phaseDurations)
  );
});
