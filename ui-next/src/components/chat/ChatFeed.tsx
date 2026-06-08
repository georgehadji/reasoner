'use client';

import { useState, useCallback, useEffect, memo } from 'react';
import { motion } from 'framer-motion';
import { Copy, Check, Sparkles, Clock, FileText, Image as ImageIcon, Wand2, Download, X, ThumbsUp, ThumbsDown, ChevronDown } from 'lucide-react';
import { ChatMessage, MemoryBadge } from './ChatMessage';
import { MarkdownRenderer } from './MarkdownRenderer';
import { StreamingMarkdown } from './StreamingMarkdown';
import { PhaseRenderer } from '@/components/phases/PhaseRenderer';
import { ResearchProgress } from '@/components/phases/ResearchProgress';
import { ErrorMessage } from './ErrorMessage';
import { WidgetRenderer } from '@/components/widgets/WidgetRenderer';
import { TokenCount, Attachment } from '@/lib/types';
import { TIMING, TEXT_SIZES } from '@/lib/config';
import { copyToClipboard, cn } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { ManifestationVisuals } from './ManifestationVisuals';
import { Tooltip } from '@/components/ui/Tooltip';
import { useAppStore } from '@/stores/app-store';

export interface RenderedPhase {
  index: number;
  phase: number;
  name: string;
  data: unknown;
}

export interface ChatFeedMessage {
  id: string;
  role: 'user' | 'assistant' | 'error' | 'info';
  content: string;
  attachments?: Attachment[];
  phases?: RenderedPhase[];
  isStreaming?: boolean;
  currentPhaseName?: string;
  tokens?: TokenCount;
  duration?: number;
  cost?: number;
  meta?: { original?: string; enhanced?: string };
  activeAgents?: { name: string; task: string }[];
  streamingContent?: string;
  phaseModels?: string[];
  images?: { data: string; model?: string }[]; // multiple generated images
  widgets?: { widget_type: string; name: string; result: Record<string, unknown>; citations?: string[] }[];
  loadingKind?: 'image-generation';
  loadingPrompt?: string;
  errorType?: string | null;
  errorRetryable?: boolean | null;
  errorRetryAfter?: number | null;
  memoryCount?: number;
  researchSteps?: { step_type: string; queries: string[]; plan: string; urls: string[] }[];
}

interface ChatFeedProps {
  messages: ChatFeedMessage[];
  onScrollToBottom?: () => void;
  showNewContentIndicator?: boolean;
  phaseOpenMode?: 'auto' | 'expand' | 'collapse';
  errorPhases?: number[];
  onFeedback?: (messageId: string, rating: 'up' | 'down') => void;
  onContinueGenerating?: () => void;
  currentPhaseName?: string;
}

function PhaseIndicator({
  name,
  agents,
  models,
  researchSteps,
}: {
  name?: string;
  agents?: { name: string; task: string }[];
  models?: string[];
  researchSteps?: { step_type: string; queries: string[]; plan: string; urls: string[] }[];
}) {
  return (
    <div className="mb-3 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1">
          {TIMING.streamingBounceDelays.map((delay) => (
            <span
              key={delay}
              className="h-2 w-2 animate-bounce rounded-full bg-[var(--text-muted)]"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
        {name ? (
          <span className="text-xs font-medium text-[var(--text-muted)]">
            Running {name}…
          </span>
        ) : null}
      </div>
      {models && models.length > 0 && (
        <div className="flex flex-wrap gap-1 pl-6">
          {models.map((m) => (
            <span
              key={m}
              className="inline-flex items-center gap-1 rounded-full border border-mds-color-cool-gray/[0.4] bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-subtle)]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
              {m.split('/').pop() || m}
            </span>
          ))}
        </div>
      )}
      {agents && agents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-6">
          {agents.map((a) => (
            <Tooltip key={a.name} text={a.task}>
              <span
                className="inline-flex items-center gap-1 rounded-full border border-mds-color-cool-gray/[0.4] bg-[var(--surface-2)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-subtle)]"
              >
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent)]" />
                {a.name}
              </span>
            </Tooltip>
          ))}
        </div>
      )}
      {researchSteps && researchSteps.length > 0 && (
        <div className="pl-6">
          <ResearchProgress steps={researchSteps} />
        </div>
      )}
    </div>
  );
}

function ImageGenerationIndicator({ prompt }: { prompt?: string }) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // Average image gen is 15-40s. We'll target ~25s for the fake progress
    // but slow down as it gets closer to 99% to wait for real data.
    const duration = 25000;
    const interval = 100;
    const step = interval / duration;
    const timer = setInterval(() => {
      setProgress((p) => {
        if (p >= 0.98) return p;
        // Ease out - slow down as we approach the end
        const remaining = 1 - p;
        const slowdown = Math.max(0.2, remaining);
        return p + step * slowdown;
      });
    }, interval);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="mb-2 w-full max-w-3xl overflow-hidden rounded-[8px] border border-mds-color-cool-gray/[0.4] bg-[var(--surface)] p-4 shadow-[var(--shadow)]">
      <div className="relative overflow-hidden rounded-[8px] border border-mds-color-mid-gray/[0.5] bg-[var(--surface)]/[0.8] p-5 backdrop-blur">
        <div className="relative mb-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
            <Wand2 className="h-3.5 w-3.5" />
            Rendering Image
          </div>
          <div className="inline-flex items-center gap-1 rounded-full border border-mds-color-cool-gray/[0.4] bg-mds-color-light-gray/[0.7] px-2.5 py-1 text-caption font-medium text-[var(--surface)]">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent)]" />
            {Math.round(progress * 100)}%
          </div>
        </div>

        <ManifestationVisuals progress={progress} />

        <div className="relative mt-5 space-y-3">
          <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-2)]">
            <motion.div
              className="h-full bg-[var(--accent)] transition-all duration-300 ease-linear"
              style={{ width: `${progress * 100}%` }}
              animate={{
                opacity: [0.8, 1, 0.8],
              }}
              transition={{ duration: 2, repeat: Infinity }}
            />
          </div>
          <div className="flex items-center justify-between gap-3 text-xs text-[var(--text-muted)]">
            <span>{progress < 0.3 ? 'Sampling models...' : progress < 0.7 ? 'Diffusing...' : 'Rendering...'}</span>
            <span className="font-medium text-[var(--text-muted)]">Working…</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs.toString().padStart(2, '0')}s`;
}

function MessageActions({
  content,
  tokens,
  duration,
  cost,
  messageId,
  onFeedback,
}: {
  content: string;
  tokens?: TokenCount;
  duration?: number;
  cost?: number;
  messageId?: string;
  onFeedback?: (messageId: string, rating: 'up' | 'down') => void;
}) {
  const [copied, setCopied] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<'up' | 'down' | null>(null);

  async function handleCopy() {
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), TIMING.copiedFeedbackMs);
    }
  }

  function handleFeedback(rating: 'up' | 'down') {
    if (!messageId || !onFeedback) return;
    setFeedbackGiven(rating);
    onFeedback(messageId, rating);
  }

  const showTokens = tokens && (tokens.total ?? 0) > 0;
  const showFeedback = isEnabled('feedback-loop') && messageId && onFeedback;

  return (
    <div className="mt-2 flex items-center justify-center gap-3 text-[var(--text-muted)]">
      <button
        type="button"
        onClick={handleCopy}
        className="flex items-center gap-1 text-caption transition-colors hover:text-[var(--text)]"
        aria-label="Copy response"
      >
        {copied ? (
          <>
            <Check className="h-3.5 w-3.5 text-[var(--accent)]" /> Copied!
          </>
        ) : (
          <>
            <Copy className="h-3.5 w-3.5" /> Copy
          </>
        )}
      </button>

      {showTokens ? (
        <span className="text-xs text-[var(--text-muted)]">
          {(tokens.input ?? 0).toLocaleString()} in · {(tokens.output ?? 0).toLocaleString()} out · {(tokens.total ?? 0).toLocaleString()} total
        </span>
      ) : null}
      {cost !== undefined && cost > 0 ? (
        <span className="text-xs text-[var(--text-muted)]">
          ${cost.toFixed(4)}
        </span>
      ) : null}
      {showFeedback && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => handleFeedback('up')}
            className={cn(
              'rounded-full p-1 text-xs transition-colors',
              feedbackGiven === 'up'
                ? 'bg-mds-color-unified-core-blue-7/[0.1] text-[var(--accent)]'
                : 'text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]'
            )}
            aria-label="Thumbs up"
            disabled={feedbackGiven !== null}
          >
            <ThumbsUp className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => handleFeedback('down')}
            className={cn(
              'rounded-full p-1 text-xs transition-colors',
              feedbackGiven === 'down'
                ? 'bg-mds-color-unified-core-red-7/[0.1] text-[var(--red)]'
                : 'text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]'
            )}
            aria-label="Thumbs down"
            disabled={feedbackGiven !== null}
          >
            <ThumbsDown className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

function ContinueButton({ onContinue }: { onContinue?: () => void }) {
  const user = useAppStore((s) => s.user);
  if (!isEnabled('continue-generating') || !onContinue) return null;

  const isDisabled = !user;

  const button = (
    <button
      type="button"
      onClick={onContinue}
      className="inline-flex items-center gap-2 rounded-[5px] border border-mds-color-cool-gray/[0.4] bg-[var(--surface)] px-4 py-2 text-xs font-medium text-[var(--text-subtle)] transition-colors hover:bg-[var(--surface)] disabled:cursor-not-allowed disabled:opacity-50"
      disabled={isDisabled}
    >
      <ChevronDown className="h-3.5 w-3.5" />
      Continue reasoning…
    </button>
  );

  return (
    <div className="mt-3 flex justify-center">
      {isDisabled ? (
        <Tooltip text="Please sign in to continue your reasoning session.">
          {button}
        </Tooltip>
      ) : (
        button
      )}
    </div>
  );
}

function ChatFeedComponent({
  messages,
  onScrollToBottom,
  showNewContentIndicator,
  phaseOpenMode = 'auto',
  errorPhases = [],
  onFeedback,
  onContinueGenerating,
  currentPhaseName,
}: ChatFeedProps) {
  const [selectedImage, setSelectedImage] = useState<{ data: string; model?: string; alt: string } | null>(null);
  // Track how many phases are allowed to render for each assistant message.
  // Key: message id, Value: number of visible phases (default 1 so first phase shows immediately)
  const [visiblePhaseCounts, setVisiblePhaseCounts] = useState<Record<string, number>>({});

  const handlePhaseComplete = useCallback((msgId: string, phaseIndex: number) => {
    setVisiblePhaseCounts((prev) => {
      const current = prev[msgId] ?? 1;
      // Only advance if this is the currently visible phase
      if (phaseIndex === current - 1) {
        return { ...prev, [msgId]: current + 1 };
      }
      return prev;
    });
  }, []);

  const getDownloadName = useCallback((model?: string) => {
    const suffix = (model || 'generated-image').replace(/[^a-z0-9_-]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
    return `${suffix || 'generated-image'}.png`;
  }, []);

  const lastAssistant = messages.filter((m) => m.role === 'assistant').at(-1);
  const liveText = currentPhaseName
    ? `Running ${currentPhaseName}`
    : lastAssistant?.isStreaming
      ? 'Thinking…'
      : '';

  return (
    <div className="relative flex flex-col gap-5 px-4 py-6 sm:px-6 lg:px-8">
      {/* ARIA live region for screen readers */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {liveText}
      </div>
      {messages.map((msg) => {
        if (msg.role === 'user') {
          return (
            <div key={msg.id} className="flex w-full flex-col items-end gap-2">
              {msg.attachments && msg.attachments.length > 0 && (
                <div className="flex flex-wrap justify-end gap-2 px-1">
                  {msg.attachments.map((att) => (
                    <div
                      key={att.id}
                      className="inline-flex items-center gap-2 rounded-[8px] border border-mds-color-cool-gray/[0.4] bg-[var(--surface-2)] px-3 py-1.5 text-sm text-[var(--text-muted)]"
                    >
                      {att.previewUrl ? (
                        <img src={att.previewUrl} alt={att.name} className="h-5 w-5 rounded object-cover" />
                      ) : (
                        <FileText className="h-4 w-4 shrink-0" />
                      )}
                      <span className="max-w-[120px] truncate">{att.name}</span>
                      <span className="text-xs text-[var(--text-muted)]">
                        {(att.size / 1024 / 1024).toFixed(1)}MB
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <ChatMessage role="user">{msg.content}</ChatMessage>
            </div>
          );
        }
        if (msg.role === 'error') {
          return (
            <div key={msg.id} className="flex w-full justify-start">
              <ErrorMessage
                content={msg.content}
                errorType={msg.errorType}
                retryable={msg.errorRetryable}
                onRetry={msg.errorRetryable ? () => { /* retry handled by parent */ } : undefined}
                onEditRetry={() => { /* edit retry handled by parent */ }}
              />
            </div>
          );
        }
        if (msg.role === 'info') {
          const isEnhancedPrompt = msg.meta?.enhanced;
          if (isEnhancedPrompt) {
            return (
              <div key={msg.id} className="flex w-full justify-center px-4">
                <div className="w-full max-w-3xl rounded-[8px] border border-mds-color-cool-gray/[0.4] bg-[var(--surface-2)] px-4 py-3">
                  <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[var(--text-muted)]">
                    <Sparkles className="h-3.5 w-3.5" />
                    Prompt Enhanced
                  </div>
                  <div className="mb-2 text-sm text-[var(--text-muted)] line-through opacity-70">
                    {msg.meta?.original}
                  </div>
                  <div className="text-sm font-medium text-[var(--text)]">
                    {msg.meta?.enhanced}
                  </div>
                </div>
              </div>
            );
          }
          return (
            <div key={msg.id} className="flex w-full justify-center">
              <div className="max-w-3xl rounded-full border border-mds-color-cool-gray/[0.4] bg-[var(--surface-2)] px-4 py-2 text-sm text-[var(--text-muted)]">
                {msg.content}
              </div>
            </div>
          );
        }

        const visibleCount = visiblePhaseCounts[msg.id] ?? 1;
        const phases = msg.phases || [];
        const visiblePhases = phases.slice(0, visibleCount);
        const forceOpen = phaseOpenMode === 'expand' ? true : phaseOpenMode === 'collapse' ? false : null;

        return (
          <div key={msg.id} className="flex w-full flex-col items-center">
            <ChatMessage role="assistant">
              {msg.memoryCount !== undefined && msg.memoryCount > 0 && (
                <MemoryBadge count={msg.memoryCount} />
              )}
              {msg.loadingKind === 'image-generation' ? (
                <ImageGenerationIndicator prompt={msg.loadingPrompt} />
              ) : msg.isStreaming && (
                <PhaseIndicator
                  name={msg.currentPhaseName}
                  agents={msg.activeAgents}
                  models={msg.phaseModels}
                  researchSteps={msg.researchSteps}
                />
              )}
              {msg.images && msg.images.length > 0 && (
                <div className="mb-4 grid w-full max-w-4xl gap-4 sm:grid-cols-2">
                  {msg.images.map((img, idx) => (
                    <figure
                      key={idx}
                      className="overflow-hidden rounded-[8px] border border-mds-color-cool-gray/[0.4] bg-[var(--surface-2)] shadow-[var(--shadow)]"
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedImage({ data: img.data, model: img.model, alt: `Generated image ${idx + 1}` })}
                        className="block w-full cursor-zoom-in bg-black/5"
                        aria-label={`Open generated image ${idx + 1}`}
                      >
                        <img
                          src={img.data}
                          alt={`Generated image ${idx + 1}`}
                          className="h-full w-full max-h-[520px] object-contain"
                          loading="lazy"
                        />
                      </button>
                      <figcaption className="flex items-center justify-between gap-3 border-t border-mds-color-cool-gray/[0.4] px-3 py-2 text-xs text-[var(--text-muted)]">
                        <span className="truncate">
                          LLM model used: <span className="font-medium text-[var(--text)]">{img.model || 'unknown'}</span>
                        </span>
                        <a
                          href={img.data}
                          download={getDownloadName(img.model)}
                          onClick={(event) => event.stopPropagation()}
                          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-mds-color-cool-gray/[0.4] px-2.5 py-1 font-systemUi text-[10px] font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface)]"
                        >
                          <Download className="h-3 w-3" />
                          Download
                        </a>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              )}
              {msg.widgets && msg.widgets.length > 0 && (
                <div className="mb-4 flex w-full max-w-3xl flex-col gap-3">
                  {msg.widgets.map((widget, idx) => (
                    <WidgetRenderer key={idx} widget={widget} />
                  ))}
                </div>
              )}
              {msg.isStreaming && msg.streamingContent ? (
                <div className="whitespace-pre-wrap text-[17px] leading-relaxed text-[var(--text)]">
                  {msg.streamingContent}
                  <span className="inline-block h-[1em] w-0.5 animate-cursor-blink rounded-sm bg-[var(--accent)] align-middle ml-0.5" />
                </div>
              ) : msg.streamingContent ? (
                <StreamingMarkdown text={msg.streamingContent} isStreaming={false} />
              ) : phases.length > 0 ? (
                <div className="w-full">
                  {visiblePhases.map((phase, idx) => {
                    return (
                      <div
                        key={`${msg.id}-${phase.phase}-${idx}`}
                        className="animate-phase-reveal"
                        style={{ animationDelay: `${idx * 60}ms` }}
                      >
                        <PhaseRenderer
                          phase={phase}
                          onComplete={() => handlePhaseComplete(msg.id, idx)}
                          forceOpen={forceOpen}
                          errorPhases={errorPhases}
                        />
                      </div>
                    );
                  })}
                </div>
              ) : (
                <MarkdownRenderer>{msg.content || ' '}</MarkdownRenderer>
              )}
            </ChatMessage>
            {msg.role === 'assistant' && (
              <>
                <MessageActions
                  content={msg.isStreaming ? (msg.streamingContent || msg.content) : msg.content}
                  tokens={msg.isStreaming ? undefined : msg.tokens}
                  duration={msg.isStreaming ? undefined : msg.duration}
                  cost={msg.isStreaming ? undefined : msg.cost}
                  messageId={msg.id}
                  onFeedback={msg.isStreaming ? undefined : onFeedback}
                />
                {msg.id === messages.filter((m) => m.role === 'assistant' && !m.isStreaming).at(-1)?.id &&
                  !messages.some((m) => m.isStreaming) &&
                  msg.phases?.some((p) => p.name?.toLowerCase().includes('synthesis')) && (
                  <ContinueButton onContinue={onContinueGenerating} />
                )}
              </>
            )}
          </div>
        );
      })}

      <div
        className={cn(
          'fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-300',
          selectedImage ? 'bg-black/80 opacity-100' : 'bg-black/0 opacity-0 pointer-events-none',
        )}
        onClick={() => setSelectedImage(null)}
      >
          <div
            className={cn(
              'relative flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-[8px] border border-mds-color-mid-gray/[0.1] bg-[var(--surface)] shadow-[var(--shadow)] transition-all duration-300',
              selectedImage ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-4 opacity-0 scale-95',
            )}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-mds-color-cool-gray/[0.4] px-4 py-3">
              <div className="min-w-0">
                <div className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Generated Image</div>
                <div className="truncate text-sm text-[var(--text)]">LLM model used: {selectedImage?.model || 'unknown'}</div>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={selectedImage?.data}
                  download={getDownloadName(selectedImage?.model)}
                  className="inline-flex items-center gap-2 rounded-full border border-mds-color-cool-gray/[0.4] px-3 py-1.5 text-sm font-medium text-[var(--text)] transition-colors hover:bg-[var(--surface-2)]"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download
                </a>
                <button
                  type="button"
                  onClick={() => setSelectedImage(null)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-mds-color-cool-gray/[0.4] text-[var(--text)] transition-colors hover:bg-[var(--surface-2)]"
                  aria-label="Close image preview"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex items-center justify-center bg-black/20 p-4">
              <img
                src={selectedImage?.data}
                alt={selectedImage?.alt}
                className="max-h-[78vh] w-auto max-w-full object-contain"
              />
            </div>
          </div>
        </div>

      <button
        type="button"
        onClick={onScrollToBottom}
        className={cn(
          'fixed bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--text)] shadow-[var(--shadow)] transition-all duration-300 hover:bg-[var(--surface-2)]',
          showNewContentIndicator
            ? 'translate-y-0 opacity-100'
            : 'translate-y-4 opacity-0 pointer-events-none',
        )}
      >
        New content below ↓
      </button>
    </div>
  );
}

export const ChatFeed = memo(ChatFeedComponent);
