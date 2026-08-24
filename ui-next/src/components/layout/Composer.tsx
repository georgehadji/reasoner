'use client';

import React, { useRef, useState, useEffect, useCallback, useMemo, useSyncExternalStore } from 'react';
import { useAppStore } from '@/stores/app-store';
import { EXAMPLE_PROMPTS, LIMITS, TIMING, API } from '@/lib/config';
import { cn } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';
import { useSubscription } from '@/hooks/useSubscription';
import { ArrowUp, Sparkles, Plus, X, FileText, Image as ImageIcon, Upload, Lock, Square } from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';

interface ComposerProps {
  running: boolean;
  onSubmit: () => void;
  onStop: () => void;
  centered?: boolean;
  isFollowup?: boolean;
}

const MAX_FILE_SIZE = LIMITS.maxFileSizeBytes;
const ALLOWED_TYPES = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/webp',
];

/* Pill toggles in the toolbar. 40px tall — the WCAG 2.5.5 floor — and the
   active state is a shape (the leading dot), not only a hue, so it survives
   monochrome and colour blindness. `aria-pressed` carries it to AT. */
const TOGGLE_BASE =
  'flex h-[var(--space-10)] cursor-pointer items-center gap-[var(--space-2)] rounded-[var(--radius-pill)] px-[var(--space-3)] text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] transition-colors duration-[var(--dur-micro)]';
const TOGGLE_ON = 'bg-[var(--accent-dim)] text-[var(--accent)]';
const TOGGLE_OFF = 'text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]';

function ActiveDot() {
  return <span aria-hidden="true" className="h-1.5 w-1.5 rounded-[var(--radius-pill)] bg-[var(--accent)]" />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

interface AttachmentChipProps {
  att: { id: string; type: string; previewUrl?: string; name: string; size: number };
  onRemove: (id: string) => void;
}

function AttachmentChip({ att, onRemove }: AttachmentChipProps) {
  const isImage = att.type.startsWith('image/');
  return (
    <div className="group inline-flex items-center gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] hover:border-[var(--border-strong)]">
      {isImage && att.previewUrl ? (
        <img src={att.previewUrl} alt="" className="h-5 w-5 rounded-[var(--radius-sm)] object-cover" />
      ) : (
        <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
      )}
      <span className="max-w-[18ch] truncate">{att.name}</span>
      <span className="nums-tabular font-mono text-[length:var(--text-2xs)] text-[var(--text-subtle)]">
        {formatFileSize(att.size)}
      </span>
      <button
        type="button"
        onClick={() => onRemove(att.id)}
        className="min-touch cursor-pointer rounded-[var(--radius-pill)] text-[var(--text-subtle)] transition-colors duration-[var(--dur-micro)] hover:bg-[var(--red-bg)] hover:text-[var(--red)]"
        aria-label={`Remove ${att.name}`}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

export const Composer = React.memo(ComposerComponent);

function ComposerComponent({ running, onSubmit, onStop, centered, isFollowup }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const composerText = useAppStore((s) => s.composerText);
  const setComposerText = useAppStore((s) => s.setComposerText);
  const attachments = useAppStore((s) => s.attachments);
  const addAttachment = useAppStore((s) => s.addAttachment);
  const removeAttachment = useAppStore((s) => s.removeAttachment);
  const tier = useAppStore((s) => s.tier);
  const toggleTier = useAppStore((s) => s.toggleTier);
  const isImageMode = useAppStore((s) => s.isImageMode);
  const toggleImageMode = useAppStore((s) => s.toggleImageMode);
  const hasContent = composerText.trim().length > 0 || attachments.length > 0;

  const user = useAppStore((s) => s.user);

  /* The greeting depends on the client's clock, so the server cannot render it.
     Two wrong ways to handle that, both previously tried here:
       - compute it during render behind `typeof window` + suppressHydrationWarning
         -> React then *accepts the server text as correct and never patches it*,
            so the greeting stays stuck on the fallback for the whole
            pre-interaction session (nothing else re-renders this component for a
            logged-out visitor -- `user` is not persisted by the store);
       - setState inside an effect -> works, but is what react-hooks/set-state-in-effect
         correctly flags, since an effect is not where derived state belongs.
     useSyncExternalStore is React's actual primitive for a client-only value:
     it hands back the server snapshot during SSR and hydration (so the markup
     matches with nothing suppressed), then re-renders once with the client
     snapshot. The store never emits, so this subscribes to nothing. */
  const isClient = useSyncExternalStore(
    useCallback(() => () => {}, []),
    () => true,
    () => false,
  );
  const greeting = useMemo(() => {
    if (!isClient) return 'Ready when you are';
    const hour = new Date().getHours();
    const part = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    const name = user?.email?.split('@')[0];
    return name ? `${part}, ${name}` : part;
  }, [isClient, user]);

  const [estimate, setEstimate] = useState<{ tokens: number; cost: string; duration: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileErrorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const estimateReqIdRef = useRef(0);

  function showFileError(message: string) {
    if (fileErrorTimerRef.current) clearTimeout(fileErrorTimerRef.current);
    setFileError(message);
    fileErrorTimerRef.current = setTimeout(() => setFileError(null), 4000);
  }

  const fetchEstimate = useCallback(async (text: string, preset: string) => {
    if (!text.trim() || text.trim().length < 3) { setEstimate(null); return; }
    const reqId = ++estimateReqIdRef.current;
    try {
      const { fetchWithCsrf } = await import('@/lib/security-client');
      const resp = await fetchWithCsrf(API.ESTIMATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem: text, preset }),
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (reqId !== estimateReqIdRef.current) return;
      setEstimate({
        tokens: (data.estimated_tokens_input || 0) + (data.estimated_tokens_output || 0),
        cost: data.estimated_cost_usd?.toFixed(3) || '0.000',
        duration: data.estimated_duration_seconds || 0,
      });
    } catch {
      if (reqId === estimateReqIdRef.current) setEstimate(null);
    }
  }, []);

  useEffect(() => {
    if (!isEnabled('cost-transparency')) return;
    const preset = tier === 'premium' ? 'auto-premium' : 'auto-budget';
    const timer = setTimeout(() => fetchEstimate(composerText, preset), TIMING.estimateDebounceMs);
    return () => clearTimeout(timer);
  }, [composerText, tier, fetchEstimate]);

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    requestAnimationFrame(() => {
      if (!el) return;
      el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (running) onStop();
      else onSubmit();
    } else if (e.key === 'Escape') {
      onStop();
    }
  }

  function processFiles(files: FileList | null) {
    if (!files) return;
    let added = false;
    for (const file of Array.from(files)) {
      if (attachments.length >= LIMITS.maxAttachments) { showFileError('Maximum 5 files allowed.'); break; }
      if (file.size > LIMITS.maxFileSizeBytes) { showFileError(`"${file.name}" exceeds the size limit.`); continue; }
      if (!ALLOWED_TYPES.includes(file.type)) { showFileError(`"${file.type}" is not a supported file type.`); continue; }
      addAttachment(file);
      added = true;
    }
    if (added) setFileError(null);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    processFiles(e.target.files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function clearFileError() {
    if (fileError) setFileError(null);
    if (fileErrorTimerRef.current) clearTimeout(fileErrorTimerRef.current);
  }

  function handleDragOver(e: React.DragEvent) {
    if (!isEnabled('drag-drop')) return;
    e.preventDefault(); e.stopPropagation(); setIsDragging(true);
  }
  function handleDragLeave(e: React.DragEvent) {
    if (!isEnabled('drag-drop')) return;
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
  }
  function handleDrop(e: React.DragEvent) {
    if (!isEnabled('drag-drop')) return;
    e.preventDefault(); e.stopPropagation(); setIsDragging(false);
    processFiles(e.dataTransfer.files);
  }
  function handlePaste(e: React.ClipboardEvent) {
    if (!isEnabled('drag-drop')) return;
    const files: File[] = [];
    for (const item of Array.from(e.clipboardData?.items ?? [])) {
      if (item.kind === 'file') { const f = item.getAsFile(); if (f) files.push(f); }
    }
    if (files.length > 0) {
      e.preventDefault();
      for (const file of files) {
        if (attachments.length >= LIMITS.maxAttachments) { alert(`Max ${LIMITS.maxAttachments} files.`); break; }
        if (file.size > LIMITS.maxFileSizeBytes) { alert(`"${file.name}" too large.`); continue; }
        if (!ALLOWED_TYPES.includes(file.type)) { alert(`"${file.type}" not supported.`); continue; }
        addAttachment(file);
      }
    }
  }

  /* ── Toolbar buttons ──────────────────────────────────── */
  function AttachButton() {
    const disabled = attachments.length >= LIMITS.maxAttachments || running;
    return (
      <Tooltip text="Attach files (PDF, TXT, MD, images)">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className={cn(
            'min-touch cursor-pointer rounded-[var(--radius-pill)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)]',
            disabled
              ? 'cursor-not-allowed opacity-40'
              : 'hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
          )}
          aria-label="Attach files"
        >
          <Plus className="h-5 w-5" aria-hidden="true" />
        </button>
      </Tooltip>
    );
  }

  function TierToggle() {
    const { subscription } = useSubscription();
    const isPremium = tier === 'premium';
    const isLocked = false;
    const costNum = estimate ? parseFloat(estimate.cost) : NaN;
    const costDisplay = Number.isFinite(costNum) ? costNum.toFixed(3) : '0.000';
    const tooltipText = isLocked
      ? 'Premium requires a Pro subscription'
      : estimate
        ? isPremium
          ? `Premium: ~$${costDisplay}`
          : `Budget: ~$${costDisplay}`
        : isPremium ? 'Switch to Budget' : 'Switch to Premium';

    return (
      <Tooltip text={tooltipText}>
        <button
          type="button"
          onClick={() => { if (!isLocked) toggleTier(); }}
          disabled={isLocked && !isPremium}
          className={cn(
            TOGGLE_BASE,
            isPremium
              ? TOGGLE_ON
              : isLocked
                ? 'cursor-not-allowed border-[var(--border)] text-[var(--text-subtle)] opacity-50'
                : TOGGLE_OFF,
          )}
          aria-pressed={isPremium}
          aria-disabled={isLocked && !isPremium}
        >
          {/* The glyph identifies the control and must persist; the dot is
              additive state. Swapping the icon out meant turning Premium on
              deleted the only thing that said "Premium". */}
          {isPremium && <ActiveDot />}
          {isLocked && !isPremium ? <Lock className="h-3 w-3" aria-hidden="true" /> : <Sparkles className="h-3 w-3" aria-hidden="true" />}
          Premium
        </button>
      </Tooltip>
    );
  }

  function ImageModeToggle() {
    return (
      <Tooltip text={isImageMode ? 'Image mode — switch to reasoning' : 'Switch to image generation'}>
        <button
          type="button"
          onClick={toggleImageMode}
          className={cn(TOGGLE_BASE, isImageMode ? TOGGLE_ON : TOGGLE_OFF)}
          aria-pressed={isImageMode}
        >
          {isImageMode && <ActiveDot />}
          <ImageIcon className="h-3 w-3" aria-hidden="true" />
          Image
        </button>
      </Tooltip>
    );
  }

  /* ── Send / Stop button ───────────────────────────────── */
  function ActionButton() {
    if (running) {
      return (
        <button
          type="button"
          onClick={onStop}
          className="min-touch cursor-pointer rounded-[var(--radius-pill)] bg-[var(--accent-2-dim)] text-[var(--text-2)] transition-colors duration-[var(--dur-micro)] hover:bg-[color-mix(in_oklab,var(--accent-2)_24%,transparent)]"
          aria-label="Stop generating"
        >
          <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
        </button>
      );
    }
    return (
      <button
        type="button"
        onClick={onSubmit}
        disabled={!hasContent}
        className={cn(
          'min-touch rounded-[var(--radius-pill)] font-semibold transition-colors duration-[var(--dur-micro)]',
          hasContent
            ? 'cursor-pointer bg-[var(--accent)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)] hover:shadow-[var(--accent-glow)]'
            : 'cursor-not-allowed bg-[var(--surface-3)] text-[var(--text-subtle)]',
        )}
        aria-label={isImageMode ? 'Generate image' : 'Send message'}
      >
        <ArrowUp className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }

  /* ── Input box ────────────────────────────────────────── */
  /* State ladder, weakest to strongest: rest → hover (border only) →
     focus-within (accent border + 3px accent ring + lifted shadow). Focus
     must never be quieter than hover, or keyboard users lose the caret. */
  const inputBox = (minH: number, placeholder: string) => (
    <div
      aria-busy={running}
      className={cn(
        'relative rounded-[var(--radius-xl)] border bg-[var(--surface)] shadow-[var(--shadow)] transition-[border-color,box-shadow,background-color] duration-[var(--dur-state)] ease-[var(--ease-standard)]',
        isDragging
          ? 'border-[var(--accent)] shadow-[var(--accent-glow)]'
          : running
            // Busy is --accent-2, not --accent: the focus ring below is
            // --accent, and when both used it the two states were
            // indistinguishable.
            ? 'border-[var(--accent-2)] shadow-[0_0_0_3px_var(--accent-2-dim)]'
            : 'border-[var(--border)] hover:border-[var(--border-strong)]',
        // Outside the ternary on purpose. The `running` branch previously
        // carried no focus-within rule at all, so focusing the textarea during
        // a run produced zero visual change (WCAG 2.4.7) — the textarea also
        // sets focus:outline-none, so nothing else drew a ring.
        !isDragging &&
          'focus-within:border-[var(--accent)] focus-within:shadow-[0_0_0_3px_var(--accent-dim),var(--shadow-lg)]',
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onPaste={handlePaste}
    >
      {isDragging && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-[var(--radius-xl)] border-2 border-dashed border-[var(--accent)] bg-[var(--accent-dim)]">
          <div className="flex items-center gap-[var(--space-2)] text-[length:var(--text-sm)] font-medium text-[var(--accent)]">
            <Upload className="h-5 w-5" aria-hidden="true" />
            Drop files here
          </div>
        </div>
      )}

      {fileError && (
        <div
          role="alert"
          className="mx-[var(--space-3)] mt-[var(--space-2)] rounded-[var(--radius)] border border-[var(--red-border)] bg-[var(--red-bg)] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--red)]"
        >
          {fileError}
        </div>
      )}
      <textarea
        ref={textareaRef}
        value={composerText}
        onChange={(e) => { setComposerText(e.target.value); autoResize(); clearFileError(); }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        aria-label={isImageMode ? 'Describe the image to generate' : 'Ask anything'}
        className="w-full resize-none bg-transparent px-[var(--space-5)] pt-[var(--space-4)] text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text)] transition-[height] duration-[var(--dur-micro)] ease-[var(--ease-standard)] placeholder:text-[var(--text-muted)] placeholder:transition-colors placeholder:duration-[var(--dur-micro)] focus:outline-none"
        style={{ minHeight: minH }}
      />

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-[var(--space-2)] px-[var(--space-5)] pb-[var(--space-2)] pt-[var(--space-2)]">
          {attachments.map((att) => (
            <AttachmentChip key={att.id} att={att} onRemove={removeAttachment} />
          ))}
        </div>
      )}

      {/* Toolbar sits inside the slab, on its floor — not a bordered tray.
          Left is "what goes in", right is "how it runs" then send. */}
      <div className="flex flex-wrap items-center justify-between gap-[var(--space-2)] px-[var(--space-3)] pb-[var(--space-3)] pt-[var(--space-2)]">
        <div className="flex items-center gap-[var(--space-1)]">
          <AttachButton />
        </div>
        <div className="flex items-center gap-[var(--space-1)]">
          <TierToggle />
          <ImageModeToggle />
          <ActionButton />
        </div>
      </div>

      {/* Lives in the shell, not the bottom-bar branch: the centered layout
          returned before ever rendering it, so on the empty state the attach
          button opened nothing at all. */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.webp"
        multiple
        className="hidden"
        onChange={handleFileSelect}
      />
    </div>
  );

  /* ── Centered (empty state) layout ───────────────────── */
  if (centered) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center px-[var(--gutter)] py-[var(--space-8)]">
        <div className="w-full max-w-[var(--width-chat)]">
          {/* Serif, and the only display-scale type in the app shell. The
              greeting is the one moment the product speaks before it works.
              No suppressHydrationWarning: `greeting` starts at the neutral
              server value and is replaced post-mount by the effect above, so
              there is no mismatch to suppress -- and suppressing one here
              would silence genuine future mismatches in this element. */}
          <h1 className="mb-[var(--space-8)] text-center font-serif text-[length:var(--text-4xl)] font-normal leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)]">
            {isImageMode ? 'What should we picture?' : greeting}
          </h1>

          {inputBox(96, isImageMode ? 'Describe the image you want to generate…' : 'How can I help you today?')}

          {!isImageMode && (
            <div className="mt-[var(--space-6)] flex flex-wrap justify-center gap-[var(--space-2)]">
              {EXAMPLE_PROMPTS.slice(0, 4).map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => {
                    setComposerText(prompt);
                    textareaRef.current?.focus();
                  }}
                  className="flex h-10 max-w-full cursor-pointer items-center rounded-[var(--radius-pill)] border border-[var(--border)] px-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)] transition-colors duration-[var(--dur-micro)] hover:border-[var(--border-strong)] hover:bg-[var(--surface)] hover:text-[var(--text)]"
                >
                  <span className="truncate">{prompt}</span>
                </button>
              ))}
            </div>
          )}

          <div className="mt-[var(--space-6)] text-center text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
            {isImageMode
              ? 'Enter to generate · Shift+Enter for newline'
              : `Enter to send · Shift+Enter for newline · Esc to stop`}
          </div>
        </div>
      </div>
    );
  }

  /* ── Bottom-bar layout ───────────────────────────────── */
  return (
    <div className="w-full px-[var(--gutter)] pb-[var(--space-4)] pt-[var(--space-2)]">
      <div className="mx-auto max-w-[var(--width-chat)]">
        {isFollowup && (
          <div className="mb-[var(--space-2)] flex items-center gap-[var(--space-2)] px-[var(--space-1)]">
            <span className="rounded-[var(--radius-pill)] bg-[var(--accent-2-dim)] px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)]">
              Follow-up
            </span>
            <span className="text-[length:var(--text-xs)] text-[var(--text-subtle)]">Continuing conversation</span>
          </div>
        )}

        {inputBox(28, isImageMode ? 'Describe the image you want to generate…' : 'Reply to Reasoner…')}

        <div className="mt-[var(--space-2)] flex flex-wrap items-center justify-center gap-x-[var(--space-2)] text-center text-[length:var(--text-2xs)] leading-[var(--lh-ui)] text-[var(--text-subtle)]">
          <span>
            {isImageMode
              ? 'Enter to generate · Shift+Enter for newline'
              : `Enter to send · Shift+Enter for newline · Esc to stop`}
          </span>
          {isEnabled('cost-transparency') && estimate && (
            <span className="nums-tabular font-mono">
              · ~{estimate.tokens.toLocaleString()} tokens · ~${estimate.cost} · ~{estimate.duration}s
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
