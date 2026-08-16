'use client';

import { useId, useState, memo } from 'react';
import { cn } from '@/lib/utils';
import {
  ChevronDown,
  Bot,
  Timer,
  Cpu,
  Boxes,
  Circle,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';
import { TIMING } from '@/lib/config';

interface SubagentInfo {
  name: string;
  model: string;
  tokens_in?: number;
  tokens_out?: number;
  duration_ms?: number;
  error?: string | null;
}

interface PhaseCardProps {
  index: number;
  phase: number;
  name: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  forceOpen?: boolean | null;
  className?: string;
  tokens?: { input?: number; output?: number } | null;
  models?: string[] | null;
  subagents?: SubagentInfo[] | null;
  duration?: number;
  compact?: boolean;
  status?: 'idle' | 'active' | 'completed' | 'error';
  quality?: { score: number; passed: boolean } | null;
}

/* Shared card vocabulary. `--chip-bg` (and `--chip-bg-2`, the step nested
   inside it) are set by whichever card owns the strip, so the same chip keeps
   its one-step lift on a --surface card and on a --surface-2 card without a
   tone prop threaded through every call site. */
export const CHIP =
  'inline-flex items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] ' +
  'border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] ' +
  'px-[var(--space-2)] py-[var(--space-1)]';

export const MICRO_LABEL =
  'text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-tight)] ' +
  'tracking-[var(--tracking-label)] text-[var(--text-muted)]';

export const ICON_SM = 'h-[var(--space-3)] w-[var(--space-3)] shrink-0';

export function formatModelLabel(model: string) {
  return model.split('/').pop() || model;
}

export function formatDurationMs(ms: number) {
  if (ms < TIMING.durationFormatMsThreshold) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/* Status is never carried by hue alone: each state has its own glyph and an
   off-screen word, so it survives monochrome, colour blindness and audio. */
const STATUS_MARK = {
  idle: { Icon: Circle, cls: 'text-[var(--text-muted)]', label: 'Not started' },
  active: {
    Icon: Loader2,
    cls: 'text-[var(--accent)] animate-spin motion-reduce:animate-none',
    label: 'Running',
  },
  completed: { Icon: CheckCircle2, cls: 'text-[var(--ok)]', label: 'Completed' },
  error: { Icon: AlertTriangle, cls: 'text-[var(--red)]', label: 'Failed' },
} as const;

function StatusMark({ status }: { status: keyof typeof STATUS_MARK }) {
  const { Icon, cls, label } = STATUS_MARK[status];
  return (
    <span className="inline-flex shrink-0 items-center">
      <Icon aria-hidden="true" className={cn(ICON_SM, cls)} />
      <span className="sr-only">{label}</span>
    </span>
  );
}

/* A 0–10 score read as digits alone forces the eye to do arithmetic on every
   row. The track carries the magnitude in FORM; the digits stay tabular so
   they hold their column while a phase is still streaming. */
export function ScoreMeter({
  value,
  max = 10,
  className,
}: {
  value: number;
  max?: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <span
      aria-hidden="true"
      className={cn(
        'block h-[var(--space-1)] overflow-hidden rounded-[var(--radius-pill)] bg-[var(--surface-3)]',
        className
      )}
    >
      <span
        className="block h-full rounded-[var(--radius-pill)] bg-[var(--accent)] transition-[width] duration-[var(--dur-state)] ease-[var(--ease-standard)]"
        style={{ width: `${pct}%` }}
      />
    </span>
  );
}

export function QualityChip({ quality }: { quality: { score: number; passed: boolean } }) {
  const Icon = quality.passed ? CheckCircle2 : AlertTriangle;
  return (
    <Tooltip text={`Quality score: ${quality.score.toFixed(1)} out of 10`}>
      <span className={cn(CHIP, 'gap-[var(--space-2)]')}>
        <Icon
          aria-hidden="true"
          className={cn(ICON_SM, quality.passed ? 'text-[var(--ok)]' : 'text-[var(--warn)]')}
        />
        <span className={MICRO_LABEL}>Quality</span>
        <ScoreMeter value={quality.score} className="w-[var(--space-8)]" />
        <span className="nums-tabular font-medium text-[var(--text-2)]">
          {quality.score.toFixed(1)}/10
        </span>
      </span>
    </Tooltip>
  );
}

/* Metrics strip — shared by PhaseCard and SynthesisCard. Every figure here is
   compared down the page (this phase vs. the next), so all of them are tabular. */
export function PhaseMetaStrip({
  tokens,
  models,
  subagents,
  duration,
  quality,
  className,
}: {
  tokens?: { input?: number; output?: number } | null;
  models?: string[] | null;
  subagents?: SubagentInfo[] | null;
  duration?: number;
  quality?: { score: number; passed: boolean } | null;
  className?: string;
}) {
  const subagentTooltip = subagents
    ? subagents
        .map((s) => `${s.name} → ${formatModelLabel(s.model)}${s.error ? ' [error]' : ''}`)
        .join('\n')
    : '';

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-[var(--space-2)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]',
        className
      )}
    >
      {quality ? <QualityChip quality={quality} /> : null}
      <span className={CHIP}>
        <Boxes aria-hidden="true" className={ICON_SM} />
        <span className="nums-tabular">
          {(tokens?.input ?? 0).toLocaleString()} in · {(tokens?.output ?? 0).toLocaleString()} out
        </span>
      </span>
      {duration !== undefined && duration > 0 ? (
        <span className={CHIP}>
          <Timer aria-hidden="true" className={ICON_SM} />
          <span className="nums-tabular">{duration.toFixed(1)}s</span>
        </span>
      ) : null}
      {models?.map((model) => (
        <Tooltip key={model} text={model}>
          <span className={CHIP}>
            <Cpu aria-hidden="true" className={ICON_SM} />
            <span className="ligatures-off">{formatModelLabel(model)}</span>
          </span>
        </Tooltip>
      ))}
      {subagents && subagents.length > 0 ? (
        <Tooltip text={subagentTooltip}>
          <span className={CHIP}>
            <Bot aria-hidden="true" className={ICON_SM} />
            <span className="nums-tabular">{subagents.length}</span>
            <span>subagent{subagents.length > 1 ? 's' : ''}</span>
          </span>
        </Tooltip>
      ) : null}
    </div>
  );
}

export function SubagentStrip({ subagents }: { subagents: SubagentInfo[] }) {
  if (!subagents.length) return null;
  return (
    <section className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-[var(--space-3)]">
      <h3 className={cn(MICRO_LABEL, 'mb-[var(--space-2)]')}>Subagents</h3>
      <div className="flex flex-wrap gap-[var(--space-2)]">
        {subagents.map((s) => {
          const el = (
            <div
              key={s.name}
              className={cn(
                // min-w-0 + flex-wrap: flex items default to min-width:auto, so
                // this row could not shrink. At 390px it needed ~385px against
                // ~326px available and the card's overflow-hidden clipped the
                // duration and part of the token count with no scrollbar.
                'flex min-w-0 flex-wrap items-center gap-x-[var(--space-2)] gap-y-[var(--space-1)] rounded-[var(--radius-sm)] px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--text-xs)] leading-[var(--lh-ui)]',
                s.error
                  ? 'border border-[var(--red-border)] bg-[var(--red-bg)] text-[var(--red)]'
                  : 'border border-[var(--border)] bg-[var(--chip-bg-2,var(--surface))] text-[var(--text-subtle)]'
              )}
            >
              {s.error ? (
                <>
                  <AlertTriangle aria-hidden="true" className={ICON_SM} />
                  <span className="sr-only">Failed:</span>
                </>
              ) : (
                <Bot aria-hidden="true" className={ICON_SM} />
              )}
              <span className="font-medium text-[var(--text)]">{s.name}</span>
              <span aria-hidden="true" className="text-[var(--text-muted)]">
                →
              </span>
              <span className="min-w-0 truncate">{formatModelLabel(s.model)}</span>
              <span className="nums-tabular text-[var(--text-muted)]">
                {s.tokens_in ?? 0}+{s.tokens_out ?? 0} tok
              </span>
              <span className="nums-tabular text-[var(--text-muted)]">
                · {formatDurationMs(s.duration_ms ?? 0)}
              </span>
            </div>
          );
          return s.error ? (
            <Tooltip key={s.name} text={s.error}>
              {el}
            </Tooltip>
          ) : (
            el
          );
        })}
      </div>
    </section>
  );
}

export const PhaseCard = memo(function PhaseCard({
  index,
  phase,
  name,
  children,
  defaultOpen = true,
  forceOpen = null,
  className,
  tokens,
  models,
  subagents,
  duration,
  compact = false,
  status = 'idle',
  quality,
}: PhaseCardProps) {
  const [userOpen, setUserOpen] = useState(defaultOpen);
  const open = forceOpen !== null ? forceOpen : userOpen;

  const uid = useId();
  const triggerId = `${uid}-trigger`;
  const panelId = `${uid}-panel`;
  const collapsed = compact && !open;

  return (
    <section
      className={cn(
        'mb-[var(--space-4)] overflow-hidden rounded-[var(--radius-lg)]',
        'border border-[var(--border)] bg-[var(--surface)]',
        '[--chip-bg:var(--surface-2)] [--chip-bg-2:var(--surface)]',
        className
      )}
    >
      <h2 className="m-0">
        <button
          type="button"
          id={triggerId}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setUserOpen((v) => !v)}
          className={cn(
            'flex min-h-[var(--space-10)] w-full items-center justify-between gap-[var(--space-3)] text-left',
            'transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-hover)]',
            collapsed
              ? 'px-[var(--space-3)] py-[var(--space-2)]'
              : 'px-[var(--space-4)] pb-[var(--space-2)] pt-[var(--space-3)]'
          )}
        >
          <span className="flex min-w-0 flex-1 items-center gap-[var(--space-2)]">
            <StatusMark status={status} />
            {collapsed ? (
              <>
                <span className="truncate text-[length:var(--text-sm)] font-medium leading-[var(--lh-ui)] tracking-[var(--tracking-base)] text-[var(--text)]">
                  {name}
                </span>
                {duration !== undefined && duration > 0 ? (
                  <span className="nums-tabular inline-flex shrink-0 items-center gap-[var(--space-1)] text-[length:var(--text-2xs)] text-[var(--text-subtle)]">
                    <Timer aria-hidden="true" className={ICON_SM} />
                    {duration.toFixed(1)}s
                  </span>
                ) : null}
              </>
            ) : (
              <>
                <span
                  className={cn(
                    MICRO_LABEL,
                    'nums-tabular shrink-0 rounded-[var(--radius-sm)] bg-[var(--surface-2)] px-[var(--space-2)] py-[var(--space-1)]'
                  )}
                >
                  Phase {index + 1}
                </span>
                <span className="truncate text-[length:var(--text-lg)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
                  {name}
                </span>
              </>
            )}
          </span>
          <ChevronDown
            aria-hidden="true"
            className={cn(
              'h-[var(--space-4)] w-[var(--space-4)] shrink-0 text-[var(--text-muted)]',
              'transition-transform duration-[var(--dur-state)] ease-[var(--ease-standard)]',
              !open && '-rotate-90'
            )}
          />
        </button>
      </h2>

      {!collapsed ? (
        <PhaseMetaStrip
          tokens={tokens}
          models={models}
          subagents={subagents}
          duration={duration}
          quality={quality}
          className="px-[var(--space-4)] pb-[var(--space-3)]"
        />
      ) : null}

      {/* Height animation without a measured pixel value: the row interpolates
          0fr → 1fr, so the panel opens at its own natural height and reduced
          motion collapses the duration to nothing on its own. `inert` is what
          `display:none` used to do for assistive tech and the tab order —
          without it a collapsed panel stays readable and focusable. */}
      <div
        id={panelId}
        style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
        className="grid transition-[grid-template-rows] duration-[var(--dur-component)] ease-[var(--ease-standard)]"
      >
        <div className={cn('min-h-0', !open && 'overflow-hidden')} inert={!open}>
          <div className="flow [--flow-space:var(--space-3)] px-[var(--space-4)] pb-[var(--space-4)] pt-[var(--space-1)]">
            {subagents && subagents.length > 0 ? <SubagentStrip subagents={subagents} /> : null}
            {children}
          </div>
        </div>
      </div>
    </section>
  );
});
