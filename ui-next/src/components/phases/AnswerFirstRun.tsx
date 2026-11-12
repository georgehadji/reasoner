'use client';

import { useId, useState } from 'react';
import { ChevronDown, ExternalLink, ListTree } from 'lucide-react';
import { cn } from '@/lib/utils';
import { extractHeadings, finalArticle, summarizeRun, type FoundAnswer } from '@/lib/answer';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import type { RenderedPhase } from '@/components/chat/ChatFeed';
import { PhaseRenderer } from './PhaseRenderer';
import { ICON_SM, MICRO_LABEL } from './PhaseCard';

interface AnswerFirstRunProps {
  found: FoundAnswer<RenderedPhase>;
  phases: RenderedPhase[];
  forceOpen?: boolean | null;
  errorPhases?: number[];
  duration?: number;
  cost?: number;
}

/* A finished run: the answer, then the phases that produced it behind one
   disclosure. Two levels only — a row per phase, then that phase's full card —
   so the process is there when wanted and out of the way when not. While a
   run streams, ChatFeed keeps pipeline order instead; this view replaces it
   on completion. */
export function AnswerFirstRun({ found, phases, forceOpen = null, errorPhases = [], duration, cost }: AnswerFirstRunProps) {
  const [open, setOpen] = useState(forceOpen === true);
  // The feed-wide Expand/Collapse control still reaches the process, and the
  // reader can toggle it afterwards (adjusted during render, not in an effect).
  const [seenForce, setSeenForce] = useState(forceOpen);
  if (forceOpen !== seenForce) {
    setSeenForce(forceOpen);
    if (forceOpen !== null) setOpen(forceOpen);
  }

  const uid = useId();
  const triggerId = `${uid}-process-trigger`;
  const panelId = `${uid}-process-panel`;
  const label = found.kind === 'article' ? 'How this was written' : 'How this was reached';

  return (
    <div className="w-full">
      <section aria-label="Answer" className="animate-phase-reveal motion-reduce:animate-none">
        {found.kind === 'article' ? (
          <ArticleDocument data={found.answer.data} />
        ) : (
          <PhaseRenderer phase={found.answer} errorPhases={errorPhases} asAnswer />
        )}
      </section>

      <section className="mt-[var(--space-2)]">
        <h2 className="m-0">
          <button
            type="button"
            id={triggerId}
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
            className="flex min-h-[var(--space-10)] w-full flex-wrap items-center gap-x-[var(--space-3)] gap-y-[var(--space-1)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-[var(--space-4)] py-[var(--space-2)] text-left transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-hover)]"
          >
            <span className="inline-flex items-center gap-[var(--space-2)] text-[length:var(--text-sm)] font-medium leading-[var(--lh-ui)] text-[var(--text)]">
              <ListTree aria-hidden="true" className={ICON_SM} />
              {label}
            </span>
            <span className="nums-tabular min-w-0 flex-1 text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
              {summarizeRun(phases, { duration, cost })}
            </span>
            <ChevronDown
              aria-hidden="true"
              className={cn(
                'h-[var(--space-4)] w-[var(--space-4)] shrink-0 text-[var(--text-muted)]',
                'transition-transform duration-[var(--dur-state)] ease-[var(--ease-standard)]',
                !open && '-rotate-90',
              )}
            />
          </button>
        </h2>
        {open ? (
          <div id={panelId} role="region" aria-labelledby={triggerId} className="mt-[var(--space-3)]">
            {found.process.map((phase, i) => (
              <PhaseRenderer
                key={`${phase.phase}-${phase.index}-${i}`}
                phase={phase}
                forceOpen={forceOpen}
                errorPhases={errorPhases}
                row
              />
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

type Rec = Record<string, unknown>;

/* An article run's deliverable, set as a document rather than as one more
   phase log: its own headings, a contents list when it is long enough to need
   one, and the sources it cites. */
function ArticleDocument({ data }: { data: unknown }) {
  const ws = ((data as Rec)?.writing_state ?? {}) as Rec;
  const article = finalArticle(data) ?? '';
  const notice = typeof ws.confidence_notice === 'string' ? ws.confidence_notice.trim() : '';
  const sources = (Array.isArray(ws.sources_cited) ? ws.sources_cited : []) as Array<string | { title?: string; url?: string }>;
  const headings = extractHeadings(article);
  // The title leads; the contents list and any notice sit between it and the body.
  const titleLine = /^\s*#\s+[^\n]+\n?/.exec(article)?.[0] ?? '';
  const body = article.slice(titleLine.length);

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] px-[var(--space-4)] py-[var(--space-6)] sm:px-[var(--space-8)]">
      {/* MarkdownRenderer leaves heading size to its container, and nothing
          sets one, so a document's headings read as body text. The scale is
          set here, for the article only. */}
      <article
        className={cn(
          'prose-serif prose-measure mx-auto',
          '[&_h1]:mb-[var(--space-6)] [&_h1]:text-[length:var(--text-3xl)] [&_h1]:font-semibold [&_h1]:text-[var(--text)]',
          '[&_h2]:mb-[var(--space-3)] [&_h2]:mt-[var(--space-8)] [&_h2]:text-[length:var(--text-xl)] [&_h2]:font-semibold [&_h2]:text-[var(--text)]',
          '[&_h3]:mb-[var(--space-2)] [&_h3]:mt-[var(--space-6)] [&_h3]:text-[length:var(--text-lg)] [&_h3]:font-semibold [&_h3]:text-[var(--text)]',
          '[&_p]:mb-[var(--space-4)]',
        )}
      >
        {titleLine ? <MarkdownRenderer>{titleLine}</MarkdownRenderer> : null}
        {headings.length >= 3 ? (
          <nav aria-label="Contents" className="mb-[var(--space-6)]">
            <span className={cn(MICRO_LABEL, 'mb-[var(--space-2)] block')}>Contents</span>
            <ol className="flex flex-col gap-[var(--space-1)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)]">
              {headings.map((h) => (
                <li key={h.id} className={h.level === 3 ? 'pl-[var(--space-4)]' : undefined}>
                  <a
                    href={`#${h.id}`}
                    className="text-[var(--text-2)] underline-offset-[var(--space-1)] hover:text-[var(--text)] hover:underline"
                  >
                    {h.text}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}
        {notice ? (
          <div
            role="note"
            className="mb-[var(--space-6)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-4)] py-[var(--space-3)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-2)]"
          >
            <span className="font-semibold text-[var(--text)]">Confidence notice: </span>
            {notice}
          </div>
        ) : null}
        <MarkdownRenderer>{body}</MarkdownRenderer>
      </article>
      {sources.length > 0 ? (
        <section aria-label="Sources" className="mx-auto mt-[var(--space-8)] max-w-[var(--width-content)] border-t border-[var(--border)] pt-[var(--space-4)]">
          <p className={cn(MICRO_LABEL, 'mb-[var(--space-2)]')}>Sources</p>
          <ol className="flex list-decimal flex-col gap-[var(--space-1)] pl-[var(--space-5)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)]">
            {sources.map((s, i) =>
              typeof s === 'string' ? (
                <li key={i}>{s}</li>
              ) : s?.url ? (
                <li key={i}>
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-[var(--space-1)] hover:text-[var(--text)] hover:underline">
                    {s.title || s.url}
                    <ExternalLink aria-hidden="true" className={ICON_SM} />
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                </li>
              ) : null,
            )}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
