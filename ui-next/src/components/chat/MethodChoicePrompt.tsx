'use client';

import { Check, Loader2, X } from 'lucide-react';
import { GateResponse } from '@/lib/types';

function prettyMethod(method: string): string {
  return method.replace(/_/g, '-').replace(/\b\w/g, (l) => l.toUpperCase());
}

export interface MethodChoicePromptProps {
  decision: GateResponse;
  alwaysAuto: boolean;
  onChoose: (preset: string) => void;
  onToggleAlwaysAuto: () => void;
  onCancel: () => void;
}

/**
 * Shown when HyperGate's confidence in its top method pick is below
 * HYPERGATE_METHOD_THRESHOLD. Lets the user confirm the suggested method,
 * pick a runner-up, or opt out of being asked again.
 */
export function MethodChoicePrompt({
  decision,
  alwaysAuto,
  onChoose,
  onToggleAlwaysAuto,
  onCancel,
}: MethodChoicePromptProps) {
  const topPreset = decision.preset;
  const candidates = [
    { method: decision.method || '', confidence: decision.confidence, rationale: decision.reasoning || '', preset: topPreset },
    ...decision.alternatives,
  ].filter((c) => c.method && c.preset);

  return (
    <div className="flex w-full justify-center px-4">
      <div className="w-full max-w-3xl rounded-[10px] border border-[var(--border)] bg-[var(--surface-2)] p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[length:var(--text-sm)] font-medium text-[var(--text)]">
            Not sure which reasoning method fits best — pick one:
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="cursor-pointer rounded-full p-1 text-[var(--text-subtle)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text)]"
            aria-label="Cancel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-col gap-2">
          {candidates.map((c, i) => (
            <button
              key={c.method}
              type="button"
              onClick={() => onChoose(c.preset!)}
              className="group flex w-full items-start gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-left transition-colors hover:border-[var(--accent)] hover:bg-[var(--surface-3)]"
            >
              <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--border)] text-[length:var(--text-2xs)] text-[var(--text-muted)] group-hover:border-[var(--accent)]">
                {i === 0 ? <Check className="h-3 w-3" /> : i + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[length:var(--text-sm)] font-medium text-[var(--text)]">{prettyMethod(c.method)}</span>
                  {i === 0 && (
                    <span className="rounded-full bg-[color-mix(in_oklab,var(--accent)_15%,transparent)] px-2 py-0.5 text-[length:var(--text-2xs)] font-medium text-[var(--accent)]">
                      Suggested
                    </span>
                  )}
                  <span className="text-[length:var(--text-2xs)] text-[var(--text-subtle)]">{Math.round(c.confidence * 100)}% confidence</span>
                </div>
                {c.rationale && (
                  <div className="mt-0.5 text-[length:var(--text-xs)] text-[var(--text-muted)]">{c.rationale}</div>
                )}
              </div>
            </button>
          ))}
        </div>

        <label className="mt-3 flex cursor-pointer items-center gap-2 text-[length:var(--text-xs)] text-[var(--text-muted)]">
          <input
            type="checkbox"
            checked={alwaysAuto}
            onChange={onToggleAlwaysAuto}
            className="h-3.5 w-3.5 cursor-pointer rounded border-[var(--border)]"
          />
          Always pick automatically — don&apos;t ask again
        </label>
      </div>
    </div>
  );
}

export function MethodChoiceLoading() {
  return (
    <div className="flex w-full justify-center px-4">
      <div className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-[length:var(--text-sm)] text-[var(--text-muted)]">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Checking best reasoning method…
      </div>
    </div>
  );
}
