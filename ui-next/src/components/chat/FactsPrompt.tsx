'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { X } from 'lucide-react';

export const FACT_MAX_LENGTH = 200;

export interface FactsPromptProps {
  questions: string[];
  /** Non-empty answers keyed by question text; empty when skipped. */
  onSubmit: (facts: Record<string, string>) => void;
  onCancel: () => void;
}

/**
 * Shown when the gate flags a high-stakes problem and needs facts the user did
 * not give. Answering is optional for every domain: "Skip" always runs the
 * problem as written.
 */
export function FactsPrompt({ questions, onSubmit, onCancel }: FactsPromptProps) {
  const titleId = useId();
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ''));

  /* Focus the first field: the user just pressed Enter in the composer, so
     focus moves here and screen readers announce the group label with it. */
  const firstRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    firstRef.current?.focus({ preventScroll: true });
  }, []);

  const submit = (skip: boolean) => {
    const facts: Record<string, string> = {};
    if (!skip) {
      questions.forEach((q, i) => {
        const a = answers[i].trim();
        if (a) facts[q] = a;
      });
    }
    onSubmit(facts);
  };

  return (
    <div className="flex w-full justify-center px-4">
      <form
        role="group"
        aria-labelledby={titleId}
        onSubmit={(e) => {
          e.preventDefault();
          submit(false);
        }}
        className="w-full max-w-3xl rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] p-4"
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div id={titleId} className="text-[length:var(--text-sm)] font-medium text-[var(--text)]">
            A few details would make this answer more reliable. Answer what you can, or skip.
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

        <div className="flex flex-col gap-3">
          {questions.map((q, i) => {
            const id = `${titleId}-q${i}`;
            return (
              <div key={q} className="flex flex-col gap-1">
                <label htmlFor={id} className="text-[length:var(--text-xs)] text-[var(--text-muted)]">
                  {q}
                </label>
                <input
                  id={id}
                  ref={i === 0 ? firstRef : undefined}
                  type="text"
                  maxLength={FACT_MAX_LENGTH}
                  value={answers[i]}
                  onChange={(e) => setAnswers((prev) => prev.map((v, j) => (j === i ? e.target.value : v)))}
                  className="rounded-[var(--radius)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-[length:var(--text-sm)] text-[var(--text)]"
                />
              </div>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="submit"
            className="cursor-pointer rounded-[var(--radius-pill)] bg-[var(--accent)] px-4 py-1.5 text-[length:var(--text-sm)] font-medium text-[var(--accent-text)] transition-colors hover:bg-[var(--accent-hover)]"
          >
            Answer and continue
          </button>
          <button
            type="button"
            onClick={() => submit(true)}
            className="cursor-pointer rounded-[var(--radius-pill)] border border-[var(--border-strong)] px-4 py-1.5 text-[length:var(--text-sm)] text-[var(--text)] transition-colors hover:bg-[var(--surface-3)]"
          >
            Skip and answer anyway
          </button>
        </div>
      </form>
    </div>
  );
}
