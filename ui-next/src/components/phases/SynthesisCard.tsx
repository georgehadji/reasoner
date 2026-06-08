'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { ChevronDown, Sparkles, Bot, Cpu, Timer, Boxes, ListChecks, ExternalLink } from 'lucide-react';
import { SourceCard } from './SourceCard';
import { Tooltip } from '@/components/ui/Tooltip';
import { TEXT_SIZES, TIMING } from '@/lib/config';

interface SubagentInfo {
  name: string;
  model: string;
  tokens_in?: number;
  tokens_out?: number;
  duration_ms?: number;
  error?: string | null;
}

interface SourceItem {
  title?: string;
  url?: string;
  snippet?: string;
  date?: string;
  domain?: string;
}

interface CitationItem {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
}

interface SynthesisCardProps {
  index: number;
  phase: number;
  name: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  tokens?: { input?: number; output?: number } | null;
  models?: string[] | null;
  subagents?: SubagentInfo[] | null;
  duration?: number;
  highlights?: Array<{ label: string; value: number }> | null;
  sources?: SourceItem[] | null;
  citations?: CitationItem[] | null;
  layoutHints?: {
    primary_theme_color?: string;
    important_sections?: string[];
  } | null;
}

function formatModelLabel(model: string) {
  return model.split('/').pop() || model;
}

function formatDurationMs(ms: number) {
  if (ms < TIMING.durationFormatMsThreshold) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function SourcesPanel({ sources }: { sources: SourceItem[] }) {
  if (!sources.length) return null;
  return (
    <div className="mb-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <p className="mb-2 text-xs font-medium text-[var(--text-muted)]">Sources</p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {sources.map((source, i) => (
          <Tooltip key={i} text={source.snippet || source.title || ''}>
            <a
              href={source.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="flex shrink-0 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs transition-colors hover:bg-[var(--surface-3)]"
            >
            <span className={`flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] ${TEXT_SIZES.tiny} font-bold text-[var(--accent-text)]`}>
              {i + 1}
            </span>
            <div className="flex flex-col">
              <span className="max-w-[180px] truncate font-medium text-[var(--text)]">
                {source.title || 'Source'}
              </span>
              {source.domain && (
                <span className={`flex items-center gap-0.5 ${TEXT_SIZES.tiny} text-[var(--text-subtle)]`}>
                  {source.domain} <ExternalLink className="h-2.5 w-2.5" />
                </span>
              )}
            </div>
          </a>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}

export function SynthesisCard({
  index,
  phase,
  name,
  children,
  defaultOpen = true,
  tokens,
  models,
  subagents,
  duration,
  highlights,
  sources,
  citations,
  layoutHints,
}: SynthesisCardProps) {
  const [open, setOpen] = useState(defaultOpen);

  const subagentTooltip = subagents
    ? subagents
        .map(
          (s) =>
            `${s.name} → ${formatModelLabel(s.model)}${s.error ? ' [error]' : ''}`
        )
        .join('\n')
    : '';

  return (
    <div className="mb-6 overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-2)]">
      <div className="border-l-4 border-[var(--accent)]">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-[var(--surface-3)]"
        >
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-md bg-[var(--accent)] px-2 py-0.5 text-xs font-medium text-[var(--accent-text)]">
                <Sparkles className="h-3 w-3" />
                Phase {index + 1}
              </span>
              <span className="text-sm font-semibold text-[var(--text)]">{name}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-subtle)]">
              <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2 py-1">
                <Boxes className="h-3 w-3" />
                {(tokens?.input ?? 0).toLocaleString()} in · {(tokens?.output ?? 0).toLocaleString()} out
              </span>
              {duration !== undefined && duration > 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2 py-1">
                  <Timer className="h-3 w-3" />
                  {duration.toFixed(1)}s
                </span>
              ) : null}
              {models && models.length > 0
                ? models.map((model) => (
                    <Tooltip key={model} text={model}>
                      <span
                        className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2 py-1"
                      >
                        <Cpu className="h-3 w-3" />
                        {formatModelLabel(model)}
                      </span>
                    </Tooltip>
                  ))
                : null}
              {subagents && subagents.length > 0 ? (
                <Tooltip text={subagentTooltip}>
                  <span
                    className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2 py-1"
                  >
                    <Bot className="h-3 w-3" />
                    {subagents.length} subagent{subagents.length > 1 ? 's' : ''}
                  </span>
                </Tooltip>
              ) : null}
            </div>
          </div>
          <ChevronDown
            className={cn(
              'h-4 w-4 text-[var(--text-muted)] transition-transform',
              !open && '-rotate-90'
            )}
          />
        </button>
        <div className="px-4 pb-4 pt-1" style={{ display: open ? 'block' : 'none' }}>
          {highlights && highlights.length > 0 && (
            <div className="mb-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
              <p className="mb-2 text-xs font-medium text-[var(--text-muted)]">Synthesis Highlights</p>
              <div className="flex flex-wrap gap-2">
                {highlights.map((highlight) => (
                  <div
                    key={highlight.label}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-xs text-[var(--text)]"
                  >
                    <ListChecks className="h-3 w-3 text-[var(--accent)]" />
                    {highlight.value} {highlight.label}
                  </div>
                ))}
              </div>
            </div>
          )}
          {highlights && highlights.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-subtle)]">
              <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">Jump to</span>
              {highlights.map((highlight) => {
                const anchor =
                  highlight.label === 'insights'
                    ? 'critical-insights'
                    : highlight.label === 'actions'
                    ? 'action-blueprint'
                    : highlight.label === 'questions'
                    ? 'open-questions'
                    : highlight.label === 'sources'
                    ? 'sources'
                    : '';
                if (!anchor) return null;
                return (
                  <a
                    key={highlight.label}
                    href={`#${anchor}`}
                    className={`rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 ${TEXT_SIZES.tiny} font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-2)]`}
                  >
                    {highlight.label}
                  </a>
                );
              })}
            </div>
          )}
          {isEnabled('sources-panel') && sources && sources.length > 0 && <SourcesPanel sources={sources} />}
          {citations && citations.length > 0 && <SourceCard citations={citations} />}
          {subagents && subagents.length > 0 && (
            <div className="mb-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
              <p className="mb-2 text-xs font-medium text-[var(--text-muted)]">Subagents</p>
              <div className="flex flex-wrap gap-2">
                {subagents.map((s) => {
                  const el = (
                    <div
                      key={s.name}
                      className={cn(
                        'flex items-center gap-2 rounded-md px-2 py-1 text-xs',
                        s.error
                          ? 'bg-red-500/10 text-red-400'
                          : 'bg-[var(--surface-2)] text-[var(--text-subtle)]'
                      )}
                    >
                      <Bot className="h-3 w-3 shrink-0" />
                      <span className="font-medium">{s.name}</span>
                      <span className="text-[var(--text-muted)]">→</span>
                      <span>{formatModelLabel(s.model)}</span>
                      <span className="text-[var(--text-muted)]">
                        {s.tokens_in ?? 0}+{s.tokens_out ?? 0} tok
                      </span>
                      <span className="text-[var(--text-muted)]">
                        · {formatDurationMs(s.duration_ms ?? 0)}
                      </span>
                    </div>
                  );
                  return s.error ? <Tooltip key={s.name} text={s.error}>{el}</Tooltip> : el;
                })}
              </div>
            </div>
          )}
          <div className="text-[var(--text)]">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
