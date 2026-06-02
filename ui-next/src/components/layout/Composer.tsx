'use client';

import React, { useRef, useState, useEffect, useCallback } from 'react';
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
    <div className="group inline-flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-xs text-[var(--text-muted)] transition-colors hover:border-[var(--border-strong)]">
      {isImage && att.previewUrl ? (
        <img src={att.previewUrl} alt={att.name} className="h-5 w-5 rounded object-cover" />
      ) : (
        <FileText className="h-4 w-4 shrink-0" />
      )}
      <span className="max-w-[120px] truncate">{att.name}</span>
      <span className="text-[10px] text-[var(--text-subtle)]">{formatFileSize(att.size)}</span>
      <button
        type="button"
        onClick={() => onRemove(att.id)}
        className="ml-1 cursor-pointer rounded-full p-1 text-[var(--text-subtle)] transition-colors hover:bg-red-500/15 hover:text-red-400 min-touch focus-visible:outline-2 focus-visible:outline-[var(--accent)] focus-visible:outline-offset-2"
        aria-label={`Remove ${att.name}`}
      >
        <X className="h-3.5 w-3.5" />
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
    return (
      <Tooltip text="Attach files (PDF, TXT, MD, images)">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={attachments.length >= 5 || running}
          className={cn(
            'flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl border text-[var(--text-muted)] transition-all',
            attachments.length >= 5 || running
              ? 'cursor-not-allowed border-[var(--border)] opacity-40'
              : 'border-[var(--border)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
          )}
          aria-label="Attach files"
        >
          <Plus className="h-4 w-4" />
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
            'flex h-10 cursor-pointer items-center gap-1.5 rounded-xl border px-3 text-xs font-medium transition-all',
            isPremium
              ? 'border-[var(--surface-2)] bg-[var(--surface)] text-[var(--text)]'
              : isLocked
                ? 'cursor-not-allowed border-[var(--border)] text-[var(--text-subtle)] opacity-50'
                : 'border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]',
          )}
          aria-disabled={isLocked && !isPremium}
        >
          {isLocked && !isPremium ? <Lock className="h-3 w-3" /> : <Sparkles className="h-3 w-3" />}
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
          className={cn(
            'flex h-10 cursor-pointer items-center gap-1.5 rounded-xl border px-3 text-xs font-medium transition-all',
            isImageMode
              ? 'border-[var(--surface-2)] bg-[var(--surface)] text-[var(--text)]'
              : 'border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)]',
          )}
        >
          <ImageIcon className="h-3 w-3" />
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
          className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl bg-[#606060]/15 text-[#A0A0A0] transition-colors hover:bg-[#606060]/25"
          aria-label="Stop"
        >
          <Square className="h-3.5 w-3.5 fill-current" />
        </button>
      );
    }
    return (
      <button
        type="button"
        onClick={onSubmit}
        disabled={!hasContent}
        className={cn(
          'flex h-11 w-11 cursor-pointer items-center justify-center rounded-xl font-semibold text-white transition-all',
          hasContent
            ? 'bg-[var(--accent)] hover:bg-[var(--accent-hover)] hover:shadow-[var(--accent-glow)]'
            : 'bg-[var(--surface-3)] text-[var(--text-subtle)] cursor-not-allowed',
        )}
        aria-label="Send"
      >
        <ArrowUp className="h-4.5 w-4.5" />
      </button>
    );
  }

  /* ── Input box ────────────────────────────────────────── */
  const inputBox = (minH: number) => (
    <div
      className={cn(
        'relative rounded-2xl border bg-[var(--surface)] transition-all duration-300 ease-out',
        isDragging
          ? 'border-[var(--accent)] shadow-[var(--accent-glow)]'
          : running
            ? 'border-[var(--accent)]/40 shadow-[0_0_20px_rgba(59,130,246,0.10)]'
            : 'border-[var(--border)] focus-within:border-[var(--border-strong)] focus-within:shadow-[var(--shadow-lg)] focus-within:bg-[var(--surface-2)]',
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onPaste={handlePaste}
    >
      {isDragging && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-2xl border-2 border-dashed border-[var(--accent)] bg-[var(--accent-dim)]">
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--accent)]">
            <Upload className="h-5 w-5" />
            Drop files here
          </div>
        </div>
      )}

      {fileError && (
        <div className="mx-3 mt-2 rounded-lg border border-[var(--red-border)] bg-[var(--red-bg)] px-3 py-2 text-sm text-[var(--red)]">
          {fileError}
        </div>
      )}
      <textarea
        ref={textareaRef}
        value={composerText}
        onChange={(e) => { setComposerText(e.target.value); autoResize(); clearFileError(); }}
        onKeyDown={handleKeyDown}
        placeholder={isImageMode ? 'Describe the image you want to generate…' : 'Ask anything…'}
        rows={1}
        className="w-full resize-none bg-transparent px-4 py-3.5 text-[16px] leading-relaxed text-[var(--text)] placeholder:text-[var(--text-muted)] placeholder:transition-colors placeholder:duration-200 focus:outline-none transition-[height] duration-150 ease-out"
        style={{ minHeight: minH }}
      />

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 px-4 pb-2">
          {attachments.map((att) => (
            <AttachmentChip key={att.id} att={att} onRemove={removeAttachment} />
          ))}
        </div>
      )}

      <div className="flex items-center justify-between px-3 pb-3">
        <div className="flex items-center gap-1.5">
          <AttachButton />
          <div className="flex items-center gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--surface-2)]/50 p-0.5">
            <TierToggle />
            <div className="h-4 w-[1px] bg-[var(--border)] mx-0.5" />
            <ImageModeToggle />
          </div>
        </div>
        <ActionButton />
      </div>
    </div>
  );

  /* ── Centered (empty state) layout ───────────────────── */
  if (centered) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center px-4">
        <div className="w-full max-w-3xl">
          <h1 className="mb-6 text-center text-2xl font-semibold tracking-tight text-[var(--text)] sm:text-3xl">
            Brainstorm ideas
          </h1>

          {inputBox(120)}

          <div className="mt-3 text-center text-xs text-[var(--text-subtle)]">
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
    <div className="w-full px-4 pb-6 pt-2">
      <div className="mx-auto max-w-3xl">
        {isFollowup && (
          <div className="mb-2 flex items-center gap-2 px-1">
            <span className="rounded-full border border-[#808080]/30 bg-[#808080]/10 px-2.5 py-0.5 text-xs font-medium text-[#A0A0A0]">
              Follow-up
            </span>
            <span className="text-xs text-[var(--text-subtle)]">Continuing conversation</span>
          </div>
        )}

        {inputBox(28)}

        <div className="mt-2 text-center text-[11px] text-[var(--text-subtle)]">
          {isImageMode
            ? 'Enter to generate · Shift+Enter for newline'
            : `Enter to send · Shift+Enter for newline · Esc to stop`}
        </div>

        {isEnabled('cost-transparency') && estimate && (
          <div className="mt-1 text-center text-[10px] text-[var(--text-subtle)]">
            ~{estimate.tokens.toLocaleString()} tokens · ~${estimate.cost} · ~{estimate.duration}s
          </div>
        )}
      </div>

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
}
