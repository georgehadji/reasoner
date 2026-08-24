'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { Brain, Search, BookOpen, Loader2, Zap, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';
import { neuroRecall, neuroLearn, neuroSessions } from '@/lib/api-client';

interface RecallChunk {
  content: string;
  source: string;
  relevance: number;
}

interface SessionEntry {
  timestamp: string;
  prompt_preview: string;
  response_preview: string;
  session_id: string;
}

interface NeuroPanelProps {
  /** Conversation ID to scope Neuro memory to the current thread */
  conversationId?: string | null;
  /** Last user message for manual Learn */
  lastUserPrompt?: string;
  /** Last assistant response for manual Neuro Learn */
  lastAssistantResponse?: string;
}

export function NeuroPanel({ conversationId, lastUserPrompt, lastAssistantResponse }: NeuroPanelProps) {
  const isMounted = useRef(true);
  useEffect(() => {
    isMounted.current = true;
    return () => { isMounted.current = false; };
  }, []);

  const [activeTab, setActiveTab] = useState<'search' | 'recent'>('search');

  // ── Search state ──
  const [query, setQuery] = useState('');
  const [recallResults, setRecallResults] = useState<RecallChunk[]>([]);
  const [recallLoading, setRecallLoading] = useState(false);

  // ── Learn state ──
  const [learnLoading, setLearnLoading] = useState(false);
  const [learnStatus, setLearnStatus] = useState<string | null>(null);

  // ── Recent state ──
  const [recentEntries, setRecentEntries] = useState<SessionEntry[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentOffset, setRecentOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [expandedEntry, setExpandedEntry] = useState<number | null>(null);

  // ── Shared error state ──
  const [error, setError] = useState<string | null>(null);

  const handleRecall = useCallback(async () => {
    if (!query.trim()) return;
    setRecallLoading(true);
    setError(null);
    setRecallResults([]);
    try {
      const data = await neuroRecall(query.trim(), conversationId || undefined);
      setRecallResults(data.chunks || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Recall failed');
    } finally {
      setRecallLoading(false);
    }
  }, [query, conversationId]);

  const handleLearn = useCallback(async () => {
    if (!lastUserPrompt || !lastAssistantResponse) {
      setError('No conversation turn available to learn from');
      return;
    }
    setLearnLoading(true);
    setError(null);
    setLearnStatus(null);
    try {
      const data = await neuroLearn(lastUserPrompt, lastAssistantResponse, conversationId || undefined);
      setLearnStatus(data.status === 'ok' ? 'Learned successfully' : `Status: ${data.status}`);
      setTimeout(() => setLearnStatus(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Learn failed');
    } finally {
      setLearnLoading(false);
    }
  }, [lastUserPrompt, lastAssistantResponse, conversationId]);

  const loadRecent = useCallback(async (offset = 0) => {
    setRecentLoading(true);
    setError(null);
    try {
      const data = await neuroSessions(conversationId || undefined, 10, offset);
      if (!isMounted.current) return;
      const entries = data.entries || [];
      if (offset === 0) {
        setRecentEntries(entries);
      } else {
        setRecentEntries((prev) => [...prev, ...entries]);
      }
      setHasMore(entries.length === 10);
      setRecentOffset(offset + entries.length);
    } catch (err) {
      if (!isMounted.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load recent memory');
    } finally {
      if (isMounted.current) setRecentLoading(false);
    }
  }, [conversationId]);

  // Self-contained rather than calling `loadRecent(0)`: an Effect must not
  // synchronously trigger a setState chain, which is what calling the (also
  // setState-ing) `loadRecent` from here would do. `loadRecent` itself is
  // unchanged and still backs the "Load more" button below. See
  // https://react.dev/learn/you-might-not-need-an-effect#fetching-data.
  useEffect(() => {
    if (activeTab !== 'recent') return;
    let ignore = false;
    async function loadInitialPage() {
      setRecentLoading(true);
      setError(null);
      try {
        const data = await neuroSessions(conversationId || undefined, 10, 0);
        if (ignore || !isMounted.current) return;
        const entries = data.entries || [];
        setRecentEntries(entries);
        setHasMore(entries.length === 10);
        setRecentOffset(entries.length);
      } catch (err) {
        if (ignore || !isMounted.current) return;
        setError(err instanceof Error ? err.message : 'Failed to load recent memory');
      } finally {
        if (!ignore && isMounted.current) setRecentLoading(false);
      }
    }
    loadInitialPage();
    return () => {
      ignore = true;
    };
  }, [activeTab, conversationId]);

  const canLearn = !!lastUserPrompt && !!lastAssistantResponse;

  return (
    <div className="flex flex-col gap-3">
      {/* Tab switcher */}
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => setActiveTab('search')}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius)] px-2 py-1.5 text-xs font-medium transition-colors ${
            activeTab === 'search'
              ? 'bg-[var(--surface-2)] text-[var(--text)]'
              : 'text-[var(--text-muted)] hover:bg-[var(--surface-2)]'
          }`}
        >
          <Search className="h-3.5 w-3.5" />
          Search
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('recent')}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-[var(--radius)] px-2 py-1.5 text-xs font-medium transition-colors ${
            activeTab === 'recent'
              ? 'bg-[var(--surface-2)] text-[var(--text)]'
              : 'text-[var(--text-muted)] hover:bg-[var(--surface-2)]'
          }`}
        >
          <Clock className="h-3.5 w-3.5" />
          Recent
        </button>
      </div>

      {activeTab === 'search' ? (
        <>
          {/* Recall Section */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
              <Search className="h-3.5 w-3.5" />
              Recall Memory
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRecall();
                }}
                placeholder="Search past reasoning..."
                className="h-8 flex-1 rounded-md border border-[var(--border)] bg-[var(--bg)] px-2.5 text-xs text-[var(--text)] placeholder:text-[var(--text-muted)] focus:border-[var(--border-strong)] focus:outline-none"
              />
              <button
                type="button"
                onClick={handleRecall}
                disabled={recallLoading || !query.trim()}
                className="inline-flex h-8 items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-2.5 text-xs font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-3)] disabled:opacity-50"
              >
                {recallLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                Recall
              </button>
            </div>
          </div>

          {/* Results */}
          {recallResults.length > 0 && (
            <div className="flex flex-col gap-2">
              {recallResults.map((chunk, idx) => (
                <div
                  key={idx}
                  className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] p-2.5 text-xs"
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="rounded-[var(--radius-sm)] bg-[var(--accent)] px-1.5 py-0.5 text-[length:var(--text-2xs)] font-medium text-[var(--accent-text)]">
                      {(chunk.relevance * 100).toFixed(0)}%
                    </span>
                    <Tooltip text={chunk.source}>
                      <span className="truncate text-[length:var(--text-2xs)] text-[var(--text-muted)]">
                        {chunk.source}
                      </span>
                    </Tooltip>
                  </div>
                  <div className="max-h-24 overflow-y-auto whitespace-pre-wrap text-[var(--text)] leading-relaxed">
                    {chunk.content}
                  </div>
                </div>
              ))}
            </div>
          )}

          {recallResults.length === 0 && !recallLoading && query && !error && (
            <div className="text-xs text-[var(--text-muted)]">No memory chunks found.</div>
          )}

          {/* Learn Section */}
          <div className="mt-1 flex flex-col gap-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
              <BookOpen className="h-3.5 w-3.5" />
              Learn from Last Turn
            </div>
            <button
              type="button"
              onClick={handleLearn}
              disabled={learnLoading || !canLearn}
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 text-xs font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-3)] disabled:opacity-50"
            >
              {learnLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Brain className="h-3.5 w-3.5" />}
              {canLearn ? 'Learn this turn' : 'No turn to learn'}
            </button>
            {learnStatus && (
              <div className="text-xs text-[var(--accent)]">{learnStatus}</div>
            )}
          </div>
        </>
      ) : (
        /* Recent tab */
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
            <Clock className="h-3.5 w-3.5" />
            Recent Memory
          </div>

          {recentEntries.length === 0 && !recentLoading && (
            <div className="text-xs text-[var(--text-muted)]">No recent entries found.</div>
          )}

          <div className="flex flex-col gap-2">
            {recentEntries.map((entry, idx) => (
              <div
                key={idx}
                className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-2)] p-2.5 text-xs"
              >
                <button
                  type="button"
                  onClick={() => setExpandedEntry(expandedEntry === idx ? null : idx)}
                  className="flex w-full items-center justify-between text-left"
                >
                  <span className="text-[length:var(--text-2xs)] text-[var(--text-muted)]">
                    {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : 'Unknown time'}
                  </span>
                  {expandedEntry === idx ? (
                    <ChevronUp className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 text-[var(--text-muted)]" />
                  )}
                </button>
                <div className="mt-1 text-[var(--text)]">
                  <span className="font-medium">Q:</span> {entry.prompt_preview}
                </div>
                {expandedEntry === idx && (
                  <div className="mt-1 border-t border-[var(--border)] pt-1 text-[var(--text-subtle)]">
                    <span className="font-medium">A:</span> {entry.response_preview}
                  </div>
                )}
              </div>
            ))}
          </div>

          {hasMore && (
            <button
              type="button"
              onClick={() => loadRecent(recentOffset)}
              disabled={recentLoading}
              className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 text-xs font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-3)] disabled:opacity-50"
            >
              {recentLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Load more'}
            </button>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-[var(--radius)] border border-[var(--red-border)] bg-[var(--red-bg)] px-2.5 py-2 text-xs text-[var(--red)]">
          {error}
        </div>
      )}
    </div>
  );
}
