'use client';

import { useState, useCallback, useEffect, useRef, memo, type CSSProperties } from 'react';
import { Copy, Check, Sparkles, FileText, Wand2, Download, X, ThumbsUp, ThumbsDown, ChevronDown } from 'lucide-react';
import { ChatMessage, MemoryBadge } from './ChatMessage';
import { MarkdownRenderer } from './MarkdownRenderer';
import { StreamingMarkdown } from './StreamingMarkdown';
import { PhaseRenderer } from '@/components/phases/PhaseRenderer';
import { ResearchProgress } from '@/components/phases/ResearchProgress';
import { ErrorMessage } from './ErrorMessage';
import { WidgetRenderer } from '@/components/widgets/WidgetRenderer';
import { TokenCount, Attachment } from '@/lib/types';
import { TIMING } from '@/lib/config';
import { copyToClipboard, cn } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { ManifestationVisuals } from './ManifestationVisuals';
import { Tooltip } from '@/components/ui/Tooltip';
import { useAppStore } from '@/stores/app-store';

/* ── Message entrance ──────────────────────────────────────────
   One transition token for every row that lands in the feed, so a
   user turn, an error and an assistant turn arrive with the same
   gesture. `both` holds the from-state through the stagger delay, so
   a batch restored from history fades in rather than popping.
   prefers-reduced-motion removes it twice over: the global !important
   block collapses the duration, and motion-reduce drops the animation.
   ────────────────────────────────────────────────────────────── */
const ENTER = 'animate-[fade-up_var(--dur-component)_var(--ease-entrance)_both] motion-reduce:animate-none';

/* Capped at four steps (160ms): a stagger is a cadence for a batch, not
   a queue — message #40 must not wait 1.6s to appear. */
const enterDelay = (i: number): CSSProperties => ({
  animationDelay: `calc(var(--stagger-step) * ${Math.min(i, 4)})`,
});

/* Small chip shared by the model and agent lists. Model IDs are strings a
   user may retype, so they get mono + ligatures-off. */
const CHIP =
  'inline-flex items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--text-2xs)] font-medium text-[var(--text-subtle)]';

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
    <div className="mb-[var(--space-3)] flex flex-col gap-[var(--space-2)]">
      <div className="flex items-center gap-[var(--space-2)]">
        {/* Pending, not impatient: a slow opacity pulse offset by a third
            of a cycle per dot. Flattened under prefers-reduced-motion by
            the keyframe override in globals.css. */}
        <div className="flex items-center gap-[var(--space-1)]" aria-hidden="true">
          {TIMING.streamingBounceDelays.map((delay, i) => (
            <span
              key={delay}
              className="h-[var(--space-2)] w-[var(--space-2)] rounded-[var(--radius-pill)] bg-[var(--text-muted)] animate-[skeleton-pulse_var(--dur-scene)_var(--ease-standard)_infinite]"
              style={{ animationDelay: `calc(var(--dur-scene) / 3 * ${i})` }}
            />
          ))}
        </div>
        {name ? (
          <span className="text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] text-[var(--text-muted)]">
            Running {name}…
          </span>
        ) : null}
      </div>
      {models && models.length > 0 && (
        <div className="flex flex-wrap gap-[var(--space-1)] pl-[var(--space-6)]">
          {models.map((m) => (
            <span key={m} className={cn(CHIP, 'font-mono')}>
              <span className="h-1.5 w-1.5 rounded-[var(--radius-pill)] bg-[var(--accent)]" aria-hidden="true" />
              {m.split('/').pop() || m}
            </span>
          ))}
        </div>
      )}
      {agents && agents.length > 0 && (
        <div className="flex flex-wrap gap-[var(--space-1)] pl-[var(--space-6)]">
          {agents.map((a) => (
            <Tooltip key={a.name} text={a.task}>
              <span className={CHIP}>
                <span
                  className="h-1.5 w-1.5 rounded-[var(--radius-pill)] bg-[var(--accent)] animate-[skeleton-pulse_var(--dur-scene)_var(--ease-standard)_infinite]"
                  aria-hidden="true"
                />
                {a.name}
              </span>
            </Tooltip>
          ))}
        </div>
      )}
      {researchSteps && researchSteps.length > 0 && (
        <div className="pl-[var(--space-6)]">
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
    const duration = TIMING.imageGenProgressDurationMs;
    // A bar redrawing ten times a second is exactly the sustained motion the
    // preference is about. Stepping once a second lands in the same place at
    // the same time — `step` is derived from the interval — it just stops
    // being an animation.
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const interval = reduced ? 1000 : TIMING.imageGenProgressIntervalMs;
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

  const percent = Math.round(progress * 100);

  return (
    <div className="mb-[var(--space-2)] w-full max-w-[var(--width-content)] overflow-hidden rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-4)] shadow-[var(--shadow)]">
      <div className="relative overflow-hidden rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)]/[0.8] p-[var(--space-5)] backdrop-blur">
        <div className="relative mb-[var(--space-4)] flex flex-wrap items-center justify-between gap-[var(--space-3)]">
          <div className="flex items-center gap-[var(--space-2)] text-[length:var(--text-xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
            <Wand2 className="h-3.5 w-3.5" aria-hidden="true" />
            Rendering Image
          </div>
          <div className="inline-flex items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--text-xs)] font-medium text-[var(--text)]">
            <span
              className="h-[var(--space-2)] w-[var(--space-2)] rounded-[var(--radius-pill)] bg-[var(--accent)] animate-[skeleton-pulse_var(--dur-scene)_var(--ease-standard)_infinite] motion-reduce:animate-none"
              aria-hidden="true"
            />
            <span className="nums-tabular">{percent}%</span>
          </div>
        </div>

        <ManifestationVisuals progress={progress} />

        {/* `progressbar` takes presentational children, so anything inside it is
            stripped from the accessibility tree. With the role on the wrapper,
            the "Sampling models…/Diffusing…" status below was silently dropped
            and a screen reader heard only the percentage. The role belongs on
            the track, which has no text of its own to lose. */}
        <div className="relative mt-[var(--space-5)] flex flex-col gap-[var(--space-3)]">
          <div
            className="h-[var(--space-2)] overflow-hidden rounded-[var(--radius-pill)] bg-[var(--surface-2)]"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={prompt ? `Generating image: ${prompt}` : 'Generating image'}
          >
            <div
              className="h-full bg-[var(--accent)] transition-[width] duration-[var(--dur-state)] ease-linear motion-reduce:transition-none"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-[var(--space-3)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
            <span>{progress < 0.3 ? 'Sampling models...' : progress < 0.7 ? 'Diffusing...' : 'Rendering...'}</span>
            <span className="font-medium text-[var(--text-muted)]">Working…</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageActions({
  content,
  tokens,
  cost,
  messageId,
  onFeedback,
}: {
  content: string;
  tokens?: TokenCount;
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
    <div className="mt-[var(--space-2)] flex flex-wrap items-center justify-center gap-[var(--space-3)] text-[length:var(--text-xs)] text-[var(--text-muted)]">
      <button
        type="button"
        onClick={handleCopy}
        className="inline-flex min-h-[var(--space-10)] items-center gap-[var(--space-1)] rounded-[var(--radius-sm)] px-[var(--space-2)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--text)]"
        aria-label={copied ? 'Response copied to clipboard' : 'Copy response'}
      >
        {/* Icon swap AND label swap — neither the tick nor the accent hue
            is doing the work alone. */}
        {copied ? (
          <>
            <Check className="h-3.5 w-3.5 text-[var(--ok)]" aria-hidden="true" /> Copied
          </>
        ) : (
          <>
            <Copy className="h-3.5 w-3.5" aria-hidden="true" /> Copy
          </>
        )}
      </button>
      <span role="status" className="sr-only">
        {copied ? 'Response copied to clipboard' : ''}
      </span>

      {showTokens ? (
        <span className="nums-tabular font-mono text-[length:var(--text-xs)] text-[var(--text-muted)]">
          {(tokens.input ?? 0).toLocaleString()} in · {(tokens.output ?? 0).toLocaleString()} out · {(tokens.total ?? 0).toLocaleString()} total
        </span>
      ) : null}
      {cost !== undefined && cost > 0 ? (
        <span className="nums-tabular font-mono text-[length:var(--text-xs)] text-[var(--text-muted)]">
          ${cost.toFixed(4)}
        </span>
      ) : null}
      {showFeedback && (
        <div className="flex items-center gap-[var(--space-1)]">
          <button
            type="button"
            onClick={() => handleFeedback('up')}
            className={cn(
              'min-touch rounded-[var(--radius-pill)] transition-colors duration-[var(--dur-micro)]',
              feedbackGiven === 'up'
                ? 'bg-[var(--accent-dim)] text-[var(--accent)]'
                : 'text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
            )}
            aria-label="Rate this response helpful"
            aria-pressed={feedbackGiven === 'up'}
            disabled={feedbackGiven !== null}
          >
            <ThumbsUp className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => handleFeedback('down')}
            className={cn(
              'min-touch rounded-[var(--radius-pill)] transition-colors duration-[var(--dur-micro)]',
              feedbackGiven === 'down'
                ? 'bg-[var(--red-bg)] text-[var(--red)]'
                : 'text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
            )}
            aria-label="Rate this response unhelpful"
            aria-pressed={feedbackGiven === 'down'}
            disabled={feedbackGiven !== null}
          >
            <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <span role="status" className="sr-only">
            {feedbackGiven === 'up' ? 'Rated helpful' : feedbackGiven === 'down' ? 'Rated unhelpful' : ''}
          </span>
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
      className="inline-flex min-h-[var(--space-10)] items-center gap-[var(--space-2)] rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface)] px-[var(--space-4)] py-[var(--space-2)] text-[length:var(--text-xs)] font-medium text-[var(--text-subtle)] transition-colors duration-[var(--dur-micro)] hover:border-[var(--border-strong)] hover:text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-50"
      disabled={isDisabled}
    >
      <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      Continue reasoning…
    </button>
  );

  return (
    <div className="mt-[var(--space-3)] flex justify-center">
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
  /* A modal <dialog> traps Tab, closes on Escape, returns focus to the
     thumbnail that opened it, and is display:none while closed — the four
     things the hand-rolled version was doing, except it never trapped Tab, so
     focus walked out of the lightbox into the conversation behind it. It also
     picks up the `html:has(dialog[open])` scroll lock in globals.css, which a
     plain overlay div could not: the feed scrolled behind the open image and
     the page was left somewhere else once it closed. Same pattern as
     SiteHeader's nav drawer. */
  const lightboxRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = lightboxRef.current;
    if (!el) return;
    if (selectedImage && !el.open) el.showModal();
    if (!selectedImage && el.open) el.close();
  }, [selectedImage]);
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
    /* The column lives here, not on each message. Previously the feed was
       full-bleed and every child set its own max-width, so an assistant turn
       centred itself while the user bubble beside it aligned to the right
       edge of a 1440px window — the two never shared a rule. */
    <div className="relative mx-auto flex w-full max-w-[var(--width-chat)] flex-col gap-[var(--space-6)] px-[var(--gutter)] py-[var(--space-6)]">
      {/* ARIA live region for screen readers */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {liveText}
      </div>
      {messages.map((msg, i) => {
        if (msg.role === 'user') {
          return (
            <div
              key={msg.id}
              className={cn('flex w-full flex-col items-end gap-[var(--space-2)]', ENTER)}
              style={enterDelay(i)}
            >
              {msg.attachments && msg.attachments.length > 0 && (
                <div className="flex flex-wrap justify-end gap-[var(--space-2)] px-[var(--space-1)]">
                  {msg.attachments.map((att) => (
                    <div
                      key={att.id}
                      className="inline-flex items-center gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]"
                    >
                      {att.previewUrl ? (
                        <img src={att.previewUrl} alt="" className="h-5 w-5 rounded-[var(--radius-sm)] object-cover" />
                      ) : (
                        <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
                      )}
                      <span className="max-w-[18ch] truncate">{att.name}</span>
                      <span className="nums-tabular font-mono text-[length:var(--text-2xs)] text-[var(--text-muted)]">
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
            <div key={msg.id} className={cn('flex w-full justify-start', ENTER)} style={enterDelay(i)}>
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
              <div key={msg.id} className={cn('flex w-full justify-center', ENTER)} style={enterDelay(i)}>
                <div className="w-full max-w-[var(--width-content)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-4)] py-[var(--space-3)]">
                  <div className="mb-[var(--space-2)] flex items-center gap-[var(--space-2)] text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] text-[var(--text-muted)]">
                    <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                    Prompt Enhanced
                  </div>
                  <div className="mb-[var(--space-2)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)] line-through opacity-70">
                    {msg.meta?.original}
                  </div>
                  <div className="text-[length:var(--text-sm)] font-medium leading-[var(--lh-body)] text-[var(--text)]">
                    {msg.meta?.enhanced}
                  </div>
                </div>
              </div>
            );
          }
          return (
            <div key={msg.id} className={cn('flex w-full justify-center', ENTER)} style={enterDelay(i)}>
              <div className="max-w-[min(100%,var(--measure))] rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-4)] py-[var(--space-2)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
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
          <div key={msg.id} className={cn('flex w-full flex-col items-center', ENTER)} style={enterDelay(i)}>
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
                <div className="mb-[var(--space-4)] grid w-full gap-[var(--space-4)] [grid-template-columns:repeat(auto-fit,minmax(min(100%,var(--width-card-min)),1fr))]">
                  {msg.images.map((img, idx) => (
                    <figure
                      key={idx}
                      className="overflow-hidden rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] shadow-[var(--shadow)]"
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedImage({ data: img.data, model: img.model, alt: `Generated image ${idx + 1}` })}
                        className="block w-full cursor-zoom-in"
                        aria-label={`Open generated image ${idx + 1} at full size`}
                      >
                        <img
                          src={img.data}
                          alt={`Generated image ${idx + 1}`}
                          className="h-full w-full max-h-[520px] object-contain"
                          loading="lazy"
                        />
                      </button>
                      <figcaption className="flex flex-wrap items-center justify-between gap-[var(--space-3)] border-t border-[var(--border)] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
                        <span className="min-w-0 truncate">
                          LLM model used:{' '}
                          <span className="font-mono font-medium text-[var(--text)]">{img.model || 'unknown'}</span>
                        </span>
                        <a
                          href={img.data}
                          download={getDownloadName(img.model)}
                          onClick={(event) => event.stopPropagation()}
                          className="inline-flex min-h-[var(--space-10)] shrink-0 items-center gap-[var(--space-1)] rounded-[var(--radius-pill)] border border-[var(--border)] px-[var(--space-3)] font-sans text-[length:var(--text-2xs)] font-medium text-[var(--text)] transition-colors duration-[var(--dur-micro)] hover:border-[var(--border-strong)] hover:bg-[var(--surface)]"
                        >
                          <Download className="h-3 w-3" aria-hidden="true" />
                          Download
                        </a>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              )}
              {msg.widgets && msg.widgets.length > 0 && (
                <div className="mb-[var(--space-4)] flex w-full flex-col gap-[var(--space-3)]">
                  {msg.widgets.map((widget, idx) => (
                    <WidgetRenderer key={idx} widget={widget} />
                  ))}
                </div>
              )}
              {msg.isStreaming && msg.streamingContent ? (
                <div className="prose-serif prose-measure whitespace-pre-wrap text-[var(--text)]">
                  {msg.streamingContent}
                  <span
                    className="ml-0.5 inline-block h-[1em] w-0.5 animate-cursor-blink rounded-[var(--radius-sm)] bg-[var(--accent)] align-middle"
                    aria-hidden="true"
                  />
                </div>
              ) : msg.streamingContent ? (
                <div className="prose-serif prose-measure">
                  <StreamingMarkdown text={msg.streamingContent} isStreaming={false} />
                </div>
              ) : phases.length > 0 ? (
                <div className="w-full">
                  {visiblePhases.map((phase, idx) => {
                    return (
                      <div
                        key={`${msg.id}-${phase.phase}-${idx}`}
                        className="animate-phase-reveal motion-reduce:animate-none"
                        style={{ animationDelay: `calc(var(--stagger-step) * ${Math.min(idx, 4)})` }}
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
                <div className="prose-serif prose-measure">
                  <MarkdownRenderer>{msg.content || ' '}</MarkdownRenderer>
                </div>
              )}
            </ChatMessage>
            {msg.role === 'assistant' && (
              <>
                <MessageActions
                  content={msg.isStreaming ? (msg.streamingContent || msg.content) : msg.content}
                  tokens={msg.isStreaming ? undefined : msg.tokens}
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

      {/* No `display` utility on the <dialog> itself — setting one overrides the
          UA's `display:none` and leaves the closed dialog on screen. The scrim
          is a child that does the centring instead, exactly as SiteHeader does. */}
      <dialog
        ref={lightboxRef}
        aria-label="Generated image preview"
        onClose={() => setSelectedImage(null)}
        onClick={(event) => { if (event.target === event.currentTarget) setSelectedImage(null); }}
        className="m-0 h-full max-h-none w-full max-w-none border-0 bg-[var(--overlay)] p-0 text-[var(--text)]"
      >
        <div
          className="flex h-full items-center justify-center p-[var(--space-4)]"
          onClick={(event) => { if (event.target === event.currentTarget) setSelectedImage(null); }}
        >
          {/* Entry animation only. The old exit cross-fade required the node to
              stay painted while closed, which is what forced the hand-rolled
              inert/pointer-events dance in the first place. */}
          <div
            className="animate-phase-reveal relative flex max-h-full w-full max-w-[var(--width-wide)] flex-col overflow-hidden rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-lg)]"
          >
            <div className="flex items-center justify-between gap-[var(--space-3)] border-b border-[var(--border)] px-[var(--space-4)] py-[var(--space-3)]">
              <div className="min-w-0">
                <div className="text-[length:var(--text-2xs)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
                  Generated Image
                </div>
                <div className="truncate text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text)]">
                  LLM model used:{' '}
                  <span className="font-mono">{selectedImage?.model || 'unknown'}</span>
                </div>
              </div>
              <div className="flex items-center gap-[var(--space-2)]">
                <a
                  href={selectedImage?.data}
                  download={getDownloadName(selectedImage?.model)}
                  className="inline-flex min-h-[var(--space-10)] items-center gap-[var(--space-2)] rounded-[var(--radius-pill)] border border-[var(--border)] px-[var(--space-3)] text-[length:var(--text-sm)] font-medium text-[var(--text)] transition-colors duration-[var(--dur-micro)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-2)]"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  Download
                </a>
                <button
                  type="button"
                  onClick={() => setSelectedImage(null)}
                  className="min-touch rounded-[var(--radius-pill)] border border-[var(--border)] text-[var(--text)] transition-colors duration-[var(--dur-micro)] hover:bg-[var(--surface-2)]"
                  aria-label="Close image preview"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </div>
            <div className="flex items-center justify-center bg-[var(--surface-2)] p-[var(--space-4)]">
              <img
                src={selectedImage?.data}
                alt={selectedImage?.alt ?? ''}
                className="max-h-[78vh] w-auto max-w-full object-contain"
              />
            </div>
          </div>
        </div>
      </dialog>

      <button
        type="button"
        onClick={onScrollToBottom}
        inert={!showNewContentIndicator}
        className={cn(
          'fixed bottom-[var(--space-24)] left-1/2 z-30 inline-flex min-h-[var(--space-10)] -translate-x-1/2 items-center rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--surface)] px-[var(--space-4)] text-[length:var(--text-sm)] font-medium text-[var(--text)] shadow-[var(--shadow)] transition-[opacity,transform,background-color] duration-[var(--dur-state)] ease-[var(--ease-standard)] hover:bg-[var(--surface-2)]',
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
