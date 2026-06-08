'use client';

import { Search, BookOpen, Lightbulb } from 'lucide-react';

interface ResearchStep {
  step_type: string;
  queries: string[];
  plan: string;
  urls: string[];
}

interface ResearchProgressProps {
  steps: ResearchStep[];
}

const stepIcon: Record<string, React.ReactNode> = {
  searching: <Search className="h-3.5 w-3.5" />,
  reading: <BookOpen className="h-3.5 w-3.5" />,
  reasoning: <Lightbulb className="h-3.5 w-3.5" />,
};

const stepLabel: Record<string, string> = {
  searching: 'Searching',
  reading: 'Reading',
  reasoning: 'Thinking',
};

export function ResearchProgress({ steps }: ResearchProgressProps) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="mb-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <p className="mb-2 text-xs font-medium text-[var(--text-muted)]">Research Activity</p>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className="mt-0.5 shrink-0 text-[var(--accent)]">
              {stepIcon[step.step_type] || stepIcon.reasoning}
            </span>
            <div className="flex flex-col gap-0.5">
              <span className="font-medium text-[var(--text)]">
                {stepLabel[step.step_type] || 'Thinking'}:
              </span>
              {step.queries.length > 0 && (
                <span className="text-[var(--text-subtle)]">
                  {step.queries.join(', ')}
                </span>
              )}
              {step.plan && (
                <span className="text-[var(--text-subtle)] italic">
                  {step.plan}
                </span>
              )}
              {step.urls.length > 0 && (
                <span className="text-[var(--text-muted)]">
                  {step.urls.slice(0, 3).join(' → ')}
                  {step.urls.length > 3 ? ` +${step.urls.length - 3} more` : ''}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
