'use client';

import { useId, useState } from 'react';
import { cn } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { ChevronDown, Sparkles, ListChecks, ExternalLink, CornerDownRight } from 'lucide-react';
import { SourceCard } from './SourceCard';
import { Tooltip } from '@/components/ui/Tooltip';
import { CHIP, ICON_SM, MICRO_LABEL, PhaseMetaStrip, SubagentStrip } from './PhaseCard';

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

function SourcesPanel({ sources }: { sources: SourceItem[] }) {
  if (!sources.length) return null;
  return (
    /* `id` is what the "Jump to → sources" chip targets. It used to aim at the
       `### Sources` heading the markdown renderer slugifies, but the synthesis
       path omits that section, so the chip pointed at nothing. */
    <section
      id="sources"
      className="scroll-mt-24 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-[var(--space-3)]"
    >
      <h3 className={cn(MICRO_LABEL, 'mb-[var(--space-2)]')}>Sources</h3>
      <div className="flex gap-[var(--space-2)] overflow-x-auto pb-[var(--space-1)]">
        {sources.map((source, i) => (
          <Tooltip key={i} text={source.snippet || source.title || ''}>
            <a
              href={source.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="flex min-h-[var(--space-10)] shrink-0 items-center gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--chip-bg-2,var(--surface))] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-3)]"
            >
              <span className="nums-tabular flex h-[var(--space-5)] w-[var(--space-5)] shrink-0 items-center justify-center rounded-[var(--radius-pill)] bg-[var(--accent)] text-[length:var(--text-2xs)] font-bold text-[var(--accent-text)]">
                {i + 1}
              </span>
              <span className="flex flex-col">
                <span className="max-w-[22ch] truncate font-medium text-[var(--text)]">
                  {source.title || 'Source'}
                </span>
                {source.domain && (
                  <span className="flex items-center gap-[var(--space-1)] text-[length:var(--text-2xs)] text-[var(--text-subtle)]">
                    <span className="ligatures-off">{source.domain}</span>
                    <ExternalLink aria-hidden="true" className={ICON_SM} />
                    <span className="sr-only">(opens in a new tab)</span>
                  </span>
                )}
              </span>
            </a>
          </Tooltip>
        ))}
      </div>
    </section>
  );
}

const HIGHLIGHT_ANCHORS: Record<string, string> = {
  insights: 'critical-insights',
  actions: 'action-blueprint',
  questions: 'open-questions',
  sources: 'sources',
};

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

  const uid = useId();
  const triggerId = `${uid}-trigger`;
  const panelId = `${uid}-panel`;
  const sourcesPanelShown = isEnabled('sources-panel') && !!sources && sources.length > 0;

  return (
    <section
      className="mb-[var(--space-6)] overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] [--chip-bg:var(--surface)] [--chip-bg-2:var(--surface-2)]"
    >
      <div className="border-l-4 border-[var(--accent)]">
        <h2 className="m-0">
          <button
            type="button"
            id={triggerId}
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
            className="flex min-h-[var(--space-10)] w-full items-center justify-between gap-[var(--space-3)] px-[var(--space-4)] pb-[var(--space-2)] pt-[var(--space-3)] text-left transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-3)]"
          >
            <span className="flex min-w-0 flex-1 items-center gap-[var(--space-2)]">
              <span
                className={cn(
                  MICRO_LABEL,
                  'nums-tabular inline-flex shrink-0 items-center gap-[var(--space-1)] rounded-[var(--radius-sm)] bg-[var(--accent)] px-[var(--space-2)] py-[var(--space-1)] text-[var(--accent-text)]'
                )}
              >
                <Sparkles aria-hidden="true" className={ICON_SM} />
                Phase {index + 1}
              </span>
              <span className="truncate text-[length:var(--text-lg)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-snug)] text-[var(--text)]">
                {name}
              </span>
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

        <PhaseMetaStrip
          tokens={tokens}
          models={models}
          subagents={subagents}
          duration={duration}
          className="px-[var(--space-4)] pb-[var(--space-3)]"
        />

        <div
          id={panelId}
          style={{ gridTemplateRows: open ? '1fr' : '0fr' }}
          className="grid transition-[grid-template-rows] duration-[var(--dur-component)] ease-[var(--ease-standard)]"
        >
          <div className={cn('min-h-0', !open && 'overflow-hidden')} inert={!open}>
            <div className="flow [--flow-space:var(--space-3)] px-[var(--space-4)] pb-[var(--space-4)] pt-[var(--space-1)]">
              {highlights && highlights.length > 0 && (
                <section className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-[var(--space-3)]">
                  <h3 className={cn(MICRO_LABEL, 'mb-[var(--space-2)]')}>Synthesis Highlights</h3>
                  <div className="flex flex-wrap gap-[var(--space-2)]">
                    {highlights.map((highlight) => (
                      <div
                        key={highlight.label}
                        className={cn(
                          CHIP,
                          // --chip-bg-2, not --chip-bg: CHIP already resolves to
                          // the panel's own tone, so a chip left on it vanished
                          // into the panel it sits in.
                          'gap-[var(--space-2)] bg-[var(--chip-bg-2,var(--surface))] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text)]'
                        )}
                      >
                        <ListChecks aria-hidden="true" className={cn(ICON_SM, 'text-[var(--accent)]')} />
                        <span className="nums-tabular font-semibold">{highlight.value}</span>
                        <span className="text-[var(--text-2)]">{highlight.label}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {highlights && highlights.length > 0 && (
                <nav
                  aria-label="Jump to synthesis section"
                  className="flex flex-wrap items-center gap-[var(--space-2)]"
                >
                  <span className={MICRO_LABEL}>Jump to</span>
                  {highlights.map((highlight) => {
                    const anchor = HIGHLIGHT_ANCHORS[highlight.label];
                    if (!anchor) return null;
                    // The `sources` highlight counts `data.sources`, but the only
                    // element carrying id="sources" is the panel below — which is
                    // behind a flag. Without this the chip is a link to nowhere
                    // every time the flag is off.
                    if (anchor === 'sources' && !sourcesPanelShown) return null;
                    return (
                      <a
                        key={highlight.label}
                        href={`#${anchor}`}
                        className={cn(
                          CHIP,
                          'min-h-[var(--space-8)] gap-[var(--space-1)] bg-[var(--chip-bg-2,var(--surface))] text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] text-[var(--text)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-2)]'
                        )}
                      >
                        <CornerDownRight aria-hidden="true" className={ICON_SM} />
                        {highlight.label}
                      </a>
                    );
                  })}
                </nav>
              )}

              {sourcesPanelShown && <SourcesPanel sources={sources!} />}
              {citations && citations.length > 0 && <SourceCard citations={citations} />}
              {subagents && subagents.length > 0 && <SubagentStrip subagents={subagents} />}

              <div className="text-[var(--text)]">{children}</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
