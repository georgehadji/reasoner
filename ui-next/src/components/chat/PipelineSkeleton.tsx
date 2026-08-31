'use client';

import { memo } from 'react';
import { METHOD_PHASES } from '@/lib/config';

interface PipelineSkeletonProps {
  method: string;
}

export const PipelineSkeleton = memo(function PipelineSkeleton({ method }: PipelineSkeletonProps) {
  const normalized = method.replace(/_/g, '-');
  const phases = METHOD_PHASES[normalized] || METHOD_PHASES['multi-perspective'];

  return (
    <div className="w-full max-w-3xl mx-auto space-y-3 px-4 py-6">
      {phases.map((phase, i) => (
        <div
          key={phase.id}
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4"
        >
          <div className="flex items-center gap-3">
            <div
              className="h-2 w-2 rounded-full bg-[var(--surface-3)]"
              style={{
                animation: 'skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                animationDelay: `${i * 150}ms`,
              }}
            />
            <div
              className="h-4 w-32 rounded bg-[var(--surface-3)]"
              style={{
                animation: 'skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                animationDelay: `${i * 150 + 75}ms`,
              }}
            />
            {i === 0 && (
              <span className="ml-auto text-[length:var(--text-2xs)] text-[var(--text-subtle)]">Initializing…</span>
            )}
          </div>
          <div className="mt-3 space-y-2">
            <div
              className="h-3 w-full rounded bg-[var(--surface-3)]"
              style={{
                animation: 'skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                animationDelay: `${i * 150 + 150}ms`,
              }}
            />
            <div
              className="h-3 w-3/4 rounded bg-[var(--surface-3)]"
              style={{
                animation: 'skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                animationDelay: `${i * 150 + 225}ms`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
});
