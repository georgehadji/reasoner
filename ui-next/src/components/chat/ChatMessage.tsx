'use client';

import { memo } from 'react';
import { Brain } from 'lucide-react';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { TIMING } from '@/lib/config';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  children: React.ReactNode;
}

const ChatMessageComponent = ({ role, children }: ChatMessageProps) => {
  if (role === 'user') {
    return (
      <div className="flex w-full justify-end">
        {/* Neutral surface, not a filled accent slab. At --measure width an
            accent-flooded block is the loudest thing on the page, which puts
            the emphasis on the question rather than the answer — and it forces
            --accent-text, so a long prompt is read in inverted colour.
            Constrained to --measure so a pasted wall of text does not run the
            full width of a 1440px window. */}
        <div className="w-full max-w-[min(100%,var(--measure))] whitespace-pre-wrap break-words rounded-[var(--radius-lg)] bg-[var(--surface-2)] px-[var(--space-4)] py-[var(--space-3)] text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text)]">
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full justify-start">
      {/* Width comes from the feed's column now — a second max-width here
          would silently win whenever the two disagreed. */}
      <div className="w-full break-words text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text)]">
        {children}
      </div>
    </div>
  );
};

export const ChatMessage = memo(ChatMessageComponent);

export function MemoryBadge({ count }: { count: number }) {
  if (!isEnabled('memory-badge') || count <= 0) return null;
  return (
    <div className="mb-[var(--space-2)] inline-flex items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--text-2xs)] font-medium text-[var(--text-muted)]">
      <Brain className="h-3 w-3" aria-hidden="true" />
      Uses <span className="nums-tabular">{count}</span> memor{count > 1 ? 'ies' : 'y'}
    </div>
  );
}

export function StreamingIndicator() {
  return (
    <div className="flex w-full justify-start" role="status" aria-label="Assistant is responding">
      {/* Calm rather than bouncy: the same skeleton-pulse the loading
          placeholders use, offset by a third of a cycle per dot. The
          keyframe is flattened under prefers-reduced-motion in globals.css. */}
      <div className="flex items-center gap-[var(--space-1)] rounded-[var(--radius-lg)] bg-[var(--surface)] px-[var(--space-4)] py-[var(--space-3)]">
        {TIMING.streamingBounceDelays.map((delay, i) => (
          <span
            key={delay}
            aria-hidden="true"
            className="h-[var(--space-2)] w-[var(--space-2)] rounded-[var(--radius-pill)] bg-[var(--text-muted)] animate-[skeleton-pulse_var(--dur-scene)_var(--ease-standard)_infinite]"
            style={{ animationDelay: `calc(var(--dur-scene) / 3 * ${i})` }}
          />
        ))}
      </div>
    </div>
  );
}
