'use client';

import { useRef, useEffect, memo } from 'react';
import { RenderedPhase } from '@/components/chat/ChatFeed';
import { TEXT_SIZES } from '@/lib/config';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { SynthesisRenderer } from './SynthesisRenderer';
import { PhaseCard } from './PhaseCard';
import { SynthesisCard } from './SynthesisCard';
import { ClassificationCard } from './ClassificationCard';
import { CritiqueCard } from './CritiqueCard';
import { PerspectivesRenderer } from './PerspectivesRenderer';
import { buildMarkdownFromPhase } from '@/lib/markdown';
import { copyToClipboard } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { getProvenanceReport } from '@/lib/provenance';
import { ProvenanceBadge } from '@/components/provenance/ProvenanceBadge';

function isSynthesisPhase(name: string): boolean {
  return /synthesis|report|theory|conclusion|verdict|redesign|aufhebung|transfer/i.test(name);
}

interface PhaseRendererProps {
  phase: RenderedPhase;
  onComplete?: () => void;
  forceOpen?: boolean | null;
  errorPhases?: number[];
}

function getTokens(data: unknown): { input?: number; output?: number } | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const t = d.tokens;
  if (!t || typeof t !== 'object') return null;
  const tokens = t as Record<string, unknown>;
  const input = typeof tokens.input === 'number' ? tokens.input : undefined;
  const output = typeof tokens.output === 'number' ? tokens.output : undefined;
  if (input == null && output == null) return null;
  return { input, output };
}

function getModels(data: unknown): string[] | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const m = d.models;
  if (!Array.isArray(m)) return null;
  return m.filter((x): x is string => typeof x === 'string');
}

function getSubagents(data: unknown): Array<{ name: string; model: string; tokens_in?: number; tokens_out?: number; duration_ms?: number; error?: string | null }> | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const s = d.subagents;
  if (!Array.isArray(s)) return null;
  return s.filter((x): x is Record<string, unknown> => typeof x === 'object' && x !== null).map((x) => ({
    name: String(x.name || 'unknown'),
    model: String(x.model || 'unknown'),
    tokens_in: typeof x.tokens_in === 'number' ? x.tokens_in : undefined,
    tokens_out: typeof x.tokens_out === 'number' ? x.tokens_out : undefined,
    duration_ms: typeof x.duration_ms === 'number' ? x.duration_ms : undefined,
    error: x.error != null ? String(x.error) : undefined,
  }));
}

function getDuration(data: unknown): number | undefined {
  if (!data || typeof data !== 'object') return undefined;
  const d = data as Record<string, unknown>;
  const duration = d.duration;
  return typeof duration === 'number' ? duration : undefined;
}

/**
 * True when this phase recorded a caught error (a parse failure it fell back
 * from, an empty step) without failing outright. The backend sets both
 * `status: 'degraded'` and `errors` on the same `phase_complete` payload
 * (api/execution/pipeline.py) — `errors` is checked independently since it
 * existed first and older payloads may carry it without the newer flag.
 * Distinct from `errorPhases` (hard failures reported via a separate
 * `phase_error` SSE event): a degraded phase still completed and its data is
 * still real, it just earned less trust than a clean pass.
 */
function hasRecordedErrors(data: unknown): boolean {
  if (!data || typeof data !== 'object') return false;
  const d = data as Record<string, unknown>;
  if (d.status === 'degraded') return true;
  return Array.isArray(d.errors) && d.errors.length > 0;
}

function getQuality(data: unknown): { score: number; passed: boolean } | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const q = d.quality;
  if (!q || typeof q !== 'object') return null;
  const qr = q as Record<string, unknown>;
  if (typeof qr.score !== 'number') return null;
  return { score: qr.score, passed: Boolean(qr.passed) };
}

function getSynthesisSections(data: unknown): {
  criticalInsights: string[];
  actionBlueprint: Array<string | { step?: string; action?: string }>;
  openQuestions: string[];
  sources: Array<{ title?: string; url?: string }>;
} | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  return {
    criticalInsights: Array.isArray(d.critical_insights) ? (d.critical_insights as string[]) : [],
    actionBlueprint: Array.isArray(d.action_blueprint) ? (d.action_blueprint as Array<string | { step?: string; action?: string }>) : [],
    openQuestions: Array.isArray(d.open_questions) ? (d.open_questions as string[]) : [],
    sources: Array.isArray(d.sources) ? (d.sources as Array<{ title?: string; url?: string }>) : [],
  };
}

function getSynthesisHighlights(data: unknown): Array<{ label: string; value: number }> | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const highlights = [
    { label: 'insights', value: Array.isArray(d.critical_insights) ? d.critical_insights.length : 0 },
    { label: 'actions', value: Array.isArray(d.action_blueprint) ? d.action_blueprint.length : 0 },
    { label: 'questions', value: Array.isArray(d.open_questions) ? d.open_questions.length : 0 },
    { label: 'sources', value: Array.isArray(d.sources) ? d.sources.length : 0 },
  ].filter((item) => item.value > 0);
  return highlights.length > 0 ? highlights : null;
}

function getVettedContext(data: unknown): Array<Record<string, unknown>> {
  if (!data || typeof data !== 'object') return [];
  const d = data as Record<string, unknown>;
  const context = d.vetted_context;
  if (!Array.isArray(context)) return [];
  return context.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null);
}

export const PhaseRenderer = memo(function PhaseRenderer({ phase, onComplete, forceOpen = null, errorPhases = [] }: PhaseRendererProps) {
  const { index, phase: phaseNum, name, data } = phase;
  const tokens = getTokens(data);
  const models = getModels(data);
  const subagents = getSubagents(data);
  const duration = getDuration(data);
  const quality = getQuality(data);
  const synthesisHighlights = getSynthesisHighlights(data);
  const synthesisSections = getSynthesisSections(data);
  const vettedContext = getVettedContext(data);
  const isCompact = isEnabled('compact-phases') && !isSynthesisPhase(name) && phaseNum !== 0;
  const defaultOpen = isSynthesisPhase(name) || phaseNum === 0;
  const isSynth = isSynthesisPhase(name);
  const phaseTextClass = isSynth ? TEXT_SIZES.synthesis : TEXT_SIZES.phaseCard;
  const cardStatus: 'error' | 'degraded' | 'completed' = errorPhases.includes(phaseNum)
    ? 'error'
    : hasRecordedErrors(data)
      ? 'degraded'
      : 'completed';

  // Direct Response / Web Search: render inline without a phase card
  if (name === 'Direct Response' || name === 'Web Search') {
    const md = buildMarkdownFromPhase(index, phaseNum, name, data, { omitSections: ['vetted_context'] });
    return <MarkdownRenderer>{md}</MarkdownRenderer>;
  }

  // Classification
  if (
    phaseNum === 0 &&
    data &&
    typeof data === 'object' &&
    ('task_type' in data || 'rationale' in data)
  ) {
    return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
        <ClassificationCard data={data} />
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </PhaseCard>
    );
  }

  // Critique (only if there are actual scores)
  const scoresArray = data && typeof data === 'object' ? (data as Record<string, unknown>).scores : undefined;
  if (
    phaseNum === 3 &&
    data &&
    typeof data === 'object' &&
    Array.isArray(scoresArray) &&
    scoresArray.length > 0
  ) {
    return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
        <CritiqueCard data={data} />
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </PhaseCard>
    );
  }

  // Perspectives (phase 2 generation candidates — gutter of epistemic labels)
  const candidatesArray = data && typeof data === 'object' ? (data as Record<string, unknown>).candidates : undefined;
  if (name === 'Perspectives' && Array.isArray(candidatesArray) && candidatesArray.length > 0) {
    return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
        <PerspectivesRenderer candidates={candidatesArray as Array<{ perspective: string; content: string; key_insights: string[]; model_used?: string }>} />
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </PhaseCard>
    );
  }

  // Scientific state (hypotheses + falsification tests)
  const scientificState = data && typeof data === 'object' ? (data as Record<string, unknown>).scientific_state as Record<string, unknown> | undefined : undefined;
  if (
    scientificState &&
    (Array.isArray(scientificState.hypotheses) || Array.isArray(scientificState.test_results))
  ) {
    const md = buildMarkdownFromPhase(index, phaseNum, name, data, { omitSections: ['vetted_context'], omitHeading: true });
    return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
        {vettedContext.length > 0 && <VettedContextBlock items={vettedContext} />}
        <div className={`markdown-body ${phaseTextClass}`}><MarkdownRenderer>{md}</MarkdownRenderer></div>
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </PhaseCard>
    );
  }

  // Socratic state (questions + answers)
  const socraticState = data && typeof data === 'object' ? (data as Record<string, unknown>).socratic_state as Record<string, unknown> | undefined : undefined;
  if (
    socraticState &&
    (Array.isArray(socraticState.questions) || Array.isArray(socraticState.answers))
  ) {
    const md = buildMarkdownFromPhase(index, phaseNum, name, data, { omitSections: ['vetted_context'], omitHeading: true });
    return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
        {vettedContext.length > 0 && <VettedContextBlock items={vettedContext} />}
        <div className={`markdown-body ${phaseTextClass}`}><MarkdownRenderer>{md}</MarkdownRenderer></div>
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </PhaseCard>
    );
  }

  // Brainstorming state (VS idea generation → clustering → deep development)
  const brainstormingState = data && typeof data === 'object'
    ? (data as Record<string, unknown>).brainstorming_state as Record<string, unknown> | undefined
    : undefined;
  if (brainstormingState) {
    const rawIdeas = Array.isArray(brainstormingState.raw_ideas) ? brainstormingState.raw_ideas as Record<string, unknown>[] : [];
    const clusters = Array.isArray(brainstormingState.clusters) ? brainstormingState.clusters as Record<string, unknown>[] : [];
    const developments = Array.isArray(brainstormingState.developments) ? brainstormingState.developments as Record<string, unknown>[] : [];

    if (rawIdeas.length > 0 || clusters.length > 0 || developments.length > 0) {
      const tierColor: Record<string, string> = {
        conventional: 'text-[var(--text-muted)]',
        lateral: 'text-[var(--text)]',
        disruptive: 'text-[var(--accent)]',
      };

      return (
        <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
          {/* Phase 2: Raw VS ideas */}
          {rawIdeas.length > 0 && clusters.length === 0 && (
            <div className="space-y-2">
              <p className={`text-[length:var(--text-xs)] font-medium uppercase tracking-wide opacity-60 ${phaseTextClass}`}>
                {rawIdeas.length} ideas generated
              </p>
              {rawIdeas.map((idea, i) => {
                const tier = String(idea.creativity_tier ?? 'conventional');
                const prob = typeof idea.probability === 'number' ? idea.probability : null;
                return (
                  <div key={i} className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[length:var(--text-sm)] font-semibold ${phaseTextClass}`}>{String(idea.title ?? '')}</span>
                      <span className={`text-[length:var(--text-xs)] font-medium ${tierColor[tier] ?? 'text-[var(--text-muted)]'}`}>{tier}</span>
                      {prob !== null && (
                        <span className="ml-auto text-[length:var(--text-xs)] opacity-50">p={prob.toFixed(2)}</span>
                      )}
                    </div>
                    <p className={`text-[length:var(--text-xs)] opacity-70 ${phaseTextClass}`}>{String(idea.core_insight ?? idea.description ?? '')}</p>
                  </div>
                );
              })}
            </div>
          )}
          {/* Phase 3: Clusters */}
          {clusters.length > 0 && developments.length === 0 && (
            <div className="space-y-3">
              {clusters.map((cluster, ci) => {
                const clusterIdeas = Array.isArray(cluster.ideas) ? cluster.ideas as Record<string, unknown>[] : [];
                const keptIdeas = clusterIdeas.filter(i => i.keep !== false);
                return (
                  <div key={ci} className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                    <p className={`text-[length:var(--text-xs)] font-semibold uppercase tracking-wide mb-2 ${phaseTextClass}`}>{String(cluster.theme ?? `Theme ${ci + 1}`)}</p>
                    {keptIdeas.map((idea, ii) => (
                      <div key={ii} className="flex items-center gap-2 py-1 border-t border-[var(--border)]">
                        <span className={`text-[length:var(--text-xs)] flex-1 ${phaseTextClass}`}>{String(idea.title ?? '')}</span>
                        <span className="text-[length:var(--text-xs)] opacity-50">N:{String(idea.novelty ?? '—')} F:{String(idea.feasibility ?? '—')} I:{String(idea.impact ?? '—')}</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
          {/* Phase 4: Developments */}
          {developments.length > 0 && (
            <div className="space-y-4">
              {developments.map((dev, di) => {
                const steps = Array.isArray(dev.steps) ? dev.steps as string[] : [];
                const risks = Array.isArray(dev.risks) ? dev.risks as string[] : [];
                return (
                  <div key={di} className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-3 space-y-2">
                    <p className={`text-[length:var(--text-sm)] font-semibold ${phaseTextClass}`}>{String(dev.title ?? '')}</p>
                    {!!dev.use_case && <p className={`text-[length:var(--text-xs)] opacity-80 ${phaseTextClass}`}>{String(dev.use_case)}</p>}
                    {steps.length > 0 && (
                      <ol className={`text-[length:var(--text-xs)] space-y-1 list-decimal list-inside opacity-80 ${phaseTextClass}`}>
                        {steps.map((s, si) => <li key={si}>{s}</li>)}
                      </ol>
                    )}
                    {risks.length > 0 && (
                      <div>
                        <p className={`text-[length:var(--text-xs)] font-medium opacity-60 ${phaseTextClass}`}>Risks</p>
                        <ul className={`text-[length:var(--text-xs)] list-disc list-inside opacity-70 ${phaseTextClass}`}>
                          {risks.map((r, ri) => <li key={ri}>{r}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {onComplete && <CompletionTrigger onComplete={onComplete} />}
        </PhaseCard>
      );
    }
  }

  // Writing state (outline, draft, fact-check, final article)
  const writingState = data && typeof data === 'object' ? (data as Record<string, unknown>).writing_state as Record<string, unknown> | undefined : undefined;
  if (
    writingState &&
    (Array.isArray(writingState.outline) ||
     typeof writingState.article === 'string' ||
     Array.isArray(writingState.factcheck_reviews) ||
     typeof writingState.final_article === 'string')
  ) {
    const md = buildMarkdownFromPhase(index, phaseNum, name, data, { omitSections: ['vetted_context'], omitHeading: true });
    return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
        {vettedContext.length > 0 && <VettedContextBlock items={vettedContext} />}
        <div className={`markdown-body ${phaseTextClass}`}><MarkdownRenderer>{md}</MarkdownRenderer></div>
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </PhaseCard>
    );
  }

  // Synthesis
  if (
    isSynthesisPhase(name) &&
    data &&
    typeof data === 'object' &&
    ('core_solution' in data || 'action_blueprint' in data)
  ) {
    const md = buildMarkdownFromPhase(index, phaseNum, name, data, {
      omitSections: ['critical_insights', 'action_blueprint', 'open_questions', 'sources', 'vetted_context'],
      omitHeading: true,
    });
    const citations = data && typeof data === 'object' ? (data as Record<string, unknown>).citations as Array<{ url: string; title: string; snippet: string; source_type: string }> | undefined : undefined;
    const provenanceReport = getProvenanceReport(data);
    return (
      <SynthesisCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} highlights={synthesisHighlights} sources={synthesisSections?.sources} citations={citations} defaultOpen>
        {synthesisSections && (
          <div className="mb-4 grid gap-4">
            {synthesisSections.criticalInsights.length > 0 && (
              <section id="critical-insights" className="scroll-mt-24 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-4">
                <h3 className="mb-2 text-[length:var(--text-sm)] font-semibold text-[var(--text)]">Critical Insights</h3>
                <ol className="list-decimal space-y-1 pl-5 text-[length:var(--text-sm)] text-[var(--text)]">
                  {synthesisSections.criticalInsights.map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ol>
              </section>
            )}
            {synthesisSections.actionBlueprint.length > 0 && (
              <section id="action-blueprint" className="scroll-mt-24 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-4">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <h3 className="text-[length:var(--text-sm)] font-semibold text-[var(--text)]">Action Blueprint</h3>
                  <button
                    type="button"
                    onClick={() => {
                      const lines = synthesisSections.actionBlueprint.map((item, i) => {
                        if (typeof item === 'string') return `- ${item}`;
                        const step = item.step || `Step ${i + 1}`;
                        const action = item.action || '';
                        return `- ${step}: ${action}`;
                      });
                      copyToClipboard(lines.join('\n'));
                    }}
                    className={`rounded-full border border-[var(--border)] bg-[var(--chip-bg-2,var(--surface))] px-2.5 py-1 ${TEXT_SIZES.tiny} font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-3)]`}
                  >
                    Copy actions
                  </button>
                </div>
                <ul className="space-y-1 text-[length:var(--text-sm)] text-[var(--text)]">
                  {synthesisSections.actionBlueprint.map((item, i) => {
                    if (typeof item === 'string') {
                      return <li key={i}>• {item}</li>;
                    }
                    const step = item.step || `Step ${i + 1}`;
                    const action = item.action || '';
                    return (
                      <li key={i}>
                        <span className="font-semibold">{step}:</span> {action}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}
            {synthesisSections.openQuestions.length > 0 && (
              <section id="open-questions" className="scroll-mt-24 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-4">
                <h3 className="mb-2 text-[length:var(--text-sm)] font-semibold text-[var(--text)]">Open Questions</h3>
                <ul className="space-y-1 text-[length:var(--text-sm)] text-[var(--text)]">
                  {synthesisSections.openQuestions.map((item, i) => (
                    <li key={i}>• {item}</li>
                  ))}
                </ul>
              </section>
            )}

          </div>
        )}
        {provenanceReport && (
          <div className="mb-4">
            <ProvenanceBadge report={provenanceReport} />
          </div>
        )}
        <SynthesisRenderer text={md} />
        {onComplete && <CompletionTrigger onComplete={onComplete} />}
      </SynthesisCard>
    );
  }

  // Fallback to markdown for everything else
  const md = buildMarkdownFromPhase(index, phaseNum, name, data, {
    omitSections: [
      ...(isSynthesisPhase(name) ? ['critical_insights', 'action_blueprint', 'open_questions', 'sources'] as const : []),
      'vetted_context' as const
    ],
    omitHeading: true,
  });
  return (
      <PhaseCard index={index} phase={phaseNum} name={name} tokens={tokens} models={models} subagents={subagents} duration={duration} defaultOpen={defaultOpen} forceOpen={forceOpen} compact={isCompact} status={cardStatus} quality={quality}>
      {vettedContext.length > 0 && <VettedContextBlock items={vettedContext} />}
      {isSynth ? (
        <SynthesisRenderer text={md} className={phaseTextClass} />
      ) : (
        <div className={`markdown-body ${phaseTextClass}`}><MarkdownRenderer>{md}</MarkdownRenderer></div>
      )}
      {onComplete && <CompletionTrigger onComplete={onComplete} />}
    </PhaseCard>
  );
});

function VettedContextBlock({ items }: { items: Array<Record<string, unknown>> }) {
  return (
    <div className="mb-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[length:var(--text-xs)] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">Vetted Context</h3>
        <span className={`${TEXT_SIZES.tiny} text-[var(--text-subtle)]`}>{items.length} source{items.length === 1 ? '' : 's'}</span>
      </div>
      <div className="space-y-3">
        {items.map((item, idx) => {
          const title = typeof item.title === 'string' ? item.title : 'Source';
          const url = typeof item.url === 'string' ? item.url : '';
          const date = typeof item.date === 'string' ? item.date : typeof item.published === 'string' ? item.published : '';
          const summary = typeof item.summary === 'string' ? item.summary : typeof item.snippet === 'string' ? item.snippet : '';
          const keyFacts = Array.isArray(item.key_facts) ? item.key_facts : [];
          return (
            <div key={idx} className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] p-3 text-[length:var(--text-sm)] text-[var(--text)]">
              <div className="flex flex-wrap items-center gap-2">
                {url ? (
                  <a href={url} target="_blank" rel="noopener noreferrer" className="font-semibold underline">
                    {title}
                  </a>
                ) : (
                  <span className="font-semibold">{title}</span>
                )}
                {date ? <span className="text-[length:var(--text-xs)] text-[var(--text-subtle)]">{date}</span> : null}
              </div>
              {summary ? <p className="mt-2 text-[length:var(--text-sm)] text-[var(--text)]">{summary}</p> : null}
              {keyFacts.length > 0 && (
                <ul className="mt-2 space-y-1 text-[length:var(--text-sm)] text-[var(--text-subtle)]">
                  {keyFacts.slice(0, 4).map((fact, i) => (
                    <li key={i}>• {fact}</li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Helper that fires onComplete once after mount. */
function CompletionTrigger({ onComplete }: { onComplete: () => void }) {
  const fired = useRef(false);
  useEffect(() => {
    if (!fired.current) {
      fired.current = true;
      onComplete();
    }
  }, [onComplete]);
  return null;
}
