'use client';

import { ExternalLink } from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';

interface Citation {
  url: string;
  title: string;
  snippet: string;
  source_type: string;
}

interface SourceCardProps {
  citations: Citation[];
}

const badgeColor: Record<string, string> = {
  web: 'bg-blue-500/10 text-blue-400',
  academic: 'bg-violet-500/10 text-violet-400',
  discussion: 'bg-amber-500/10 text-amber-400',
  file: 'bg-emerald-500/10 text-emerald-400',
  scraped: 'bg-slate-500/10 text-slate-400',
};

export function SourceCard({ citations }: SourceCardProps) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className="mb-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <p className="mb-2 text-xs font-medium text-[var(--text-muted)]">Sources</p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {citations.map((c, i) => (
          <Tooltip key={i} text={c.snippet || c.title}>
            <a
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex shrink-0 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs transition-colors hover:bg-[var(--surface-3)]"
            >
              <span className={`flex h-5 w-5 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-[var(--accent-text)]`}>
                {i + 1}
              </span>
              <div className="flex flex-col">
                <span className="max-w-[180px] truncate font-medium text-[var(--text)]">
                  {c.title || 'Source'}
                </span>
                <div className="flex items-center gap-1">
                  <span className={`rounded px-1 py-0.5 text-[10px] font-medium ${badgeColor[c.source_type] || badgeColor.web}`}>
                    {c.source_type}
                  </span>
                  <ExternalLink className="h-2.5 w-2.5 text-[var(--text-subtle)]" />
                </div>
              </div>
            </a>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}
