'use client';

import { ExternalLink, Globe, GraduationCap, MessagesSquare, FileText, Scissors } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip } from '@/components/ui/Tooltip';
import { ICON_SM, MICRO_LABEL } from './PhaseCard';

interface Citation {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
}

interface SourceCardProps {
  citations: Citation[];
}

/* Source type used to be five hardcoded Tailwind hues, which is the one
   encoding that fails for the ~8% of readers who cannot separate amber from
   emerald — and for anyone printing the run. The glyph carries the type; the
   chip stays neutral and on-palette. */
const SOURCE_MARK: Record<string, typeof Globe> = {
  web: Globe,
  academic: GraduationCap,
  discussion: MessagesSquare,
  file: FileText,
  scraped: Scissors,
};

export function SourceCard({ citations }: SourceCardProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <section className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--chip-bg,var(--surface-2))] p-[var(--space-3)]">
      {/* "Citations", not "Sources": SynthesisCard can render this panel and
          SourcesPanel back to back, and two identical <h3>Sources</h3> in a row
          give a screen-reader user no way to tell the two lists apart. These
          are the inline-cited works; that panel is everything discovered. */}
      <h3 className={cn(MICRO_LABEL, 'mb-[var(--space-2)]')}>Citations</h3>
      <div className="flex gap-[var(--space-2)] overflow-x-auto pb-[var(--space-1)]">
        {citations.map((c, i) => {
          const Mark = SOURCE_MARK[c.source_type] ?? Globe;
          return (
            <Tooltip key={i} text={c.snippet || c.title}>
              <a
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-h-[var(--space-10)] shrink-0 items-center gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--chip-bg-2,var(--surface))] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-3)]"
              >
                <span className="nums-tabular flex h-[var(--space-5)] w-[var(--space-5)] shrink-0 items-center justify-center rounded-[var(--radius-pill)] bg-[var(--accent)] text-[length:var(--text-2xs)] font-bold text-[var(--accent-text)]">
                  {i + 1}
                </span>
                <span className="flex flex-col">
                  <span className="max-w-[22ch] truncate font-medium text-[var(--text)]">
                    {c.title || 'Source'}
                  </span>
                  <span className="flex items-center gap-[var(--space-1)] text-[length:var(--text-2xs)] text-[var(--text-muted)]">
                    <Mark aria-hidden="true" className={ICON_SM} />
                    <span className="smallcaps">{c.source_type}</span>
                    <ExternalLink aria-hidden="true" className={ICON_SM} />
                    <span className="sr-only">(opens in a new tab)</span>
                  </span>
                </span>
              </a>
            </Tooltip>
          );
        })}
      </div>
    </section>
  );
}
