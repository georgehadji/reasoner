'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
  Sparkles,
  Trash2,
  Sun,
  PanelLeft,
  Brain,
  Copy,
  ArrowUpCircle,
  Command,
  CreditCard,
  Info,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { isEnabled } from '@/hooks/useFeatureFlags';

interface CommandItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  shortcut?: string;
  action: () => void;
}

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNew: () => void;
  onClearComposer: () => void;
  onToggleTheme: () => void;
  onToggleSidebar: () => void;
  onToggleNeuro: () => void;
  onToggleTier: () => void;
  tier: string;
  onCopyLastResponse: () => void;
  recentCommands?: string[];
  onRecordCommand?: (id: string) => void;
}

export function CommandPalette({
  isOpen,
  onClose,
  onNew,
  onClearComposer,
  onToggleTheme,
  onToggleSidebar,
  onToggleNeuro,
  onToggleTier,
  tier,
  onCopyLastResponse,
  recentCommands = [],
  onRecordCommand,
}: CommandPaletteProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const router = useRouter();

  const commands: CommandItem[] = useMemo(
    () => [
      { id: 'new', label: 'New problem', icon: <Sparkles className="h-4 w-4" />, action: onNew },
      { id: 'clear', label: 'Clear composer', icon: <Trash2 className="h-4 w-4" />, shortcut: 'Ctrl+L', action: onClearComposer },
      { id: 'theme', label: 'Toggle theme', icon: <Sun className="h-4 w-4" />, action: onToggleTheme },
      { id: 'sidebar', label: 'Toggle sidebar', icon: <PanelLeft className="h-4 w-4" />, shortcut: 'B', action: onToggleSidebar },
      { id: 'neuro', label: 'Open Neuro panel', icon: <Brain className="h-4 w-4" />, action: onToggleNeuro },
      { id: 'tier', label: tier === 'premium' ? 'Switch to Budget' : 'Switch to Premium', icon: <ArrowUpCircle className="h-4 w-4" />, action: onToggleTier },
      { id: 'copy', label: 'Copy last response', icon: <Copy className="h-4 w-4" />, shortcut: 'Ctrl+Shift+C', action: onCopyLastResponse },
      { id: 'pricing', label: 'View Pricing', icon: <CreditCard className="h-4 w-4" />, action: () => { onClose(); router.push('/pricing'); } },
      { id: 'about', label: 'About Reasoner', icon: <Info className="h-4 w-4" />, action: () => { onClose(); router.push('/about'); } },
      { id: 'settings', label: 'Account Settings', icon: <Command className="h-4 w-4" />, action: () => { onClose(); router.push('/settings'); } },
    ],
    [onNew, onClearComposer, onToggleTheme, onToggleSidebar, onToggleNeuro, onToggleTier, tier, onCopyLastResponse, router, onClose]
  );

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (!isOpen) return;
    const raf = requestAnimationFrame(() => {
      setQuery('');
      setSelectedIndex(0);
      inputRef.current?.focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    function handler(e: KeyboardEvent) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => (i + 1) % filtered.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => (i - 1 + filtered.length) % filtered.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const cmd = filtered[selectedIndex];
        if (cmd) {
          cmd.action();
          onRecordCommand?.(cmd.id);
          onClose();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, filtered, selectedIndex, onClose, onRecordCommand]);

  if (!isEnabled('command-palette')) return null;

  return (
    <div
      className={cn(
        'fixed inset-0 z-[400] flex items-start justify-center p-4 pt-[20vh] transition-all duration-200',
        isOpen
          ? 'bg-[var(--scrim)] opacity-100'
          : 'bg-transparent opacity-0 pointer-events-none',
      )}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          'w-full max-w-lg overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-lg)] transition-all duration-200',
          isOpen ? 'translate-y-0 opacity-100' : '-translate-y-2 opacity-0',
        )}
      >
        <div className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3">
          <Command className="h-4 w-4 text-[var(--text-muted)]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-[length:var(--text-sm)] text-[var(--text)] outline-none placeholder:text-[var(--text-muted)]"
          />
          <kbd className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">ESC</kbd>
        </div>

        {recentCommands.length > 0 && !query && (
          <div className="px-2 py-2">
            <p className="mb-1 px-2 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Recent</p>
            {recentCommands.map((id) => {
              const cmd = commands.find((c) => c.id === id);
              if (!cmd) return null;
              return (
                <button
                  key={cmd.id}
                  type="button"
                  onClick={() => {
                    cmd.action();
                    onRecordCommand?.(cmd.id);
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-[length:var(--text-sm)] text-[var(--text)] transition-colors hover:bg-[var(--surface-2)]"
                >
                  <span className="text-[var(--text-muted)]">{cmd.icon}</span>
                  <span>{cmd.label}</span>
                </button>
              );
            })}
          </div>
        )}

        <div className="max-h-[50vh] overflow-y-auto px-2 py-2">
          {filtered.map((cmd, idx) => (
            <button
              key={cmd.id}
              type="button"
              onClick={() => {
                cmd.action();
                onRecordCommand?.(cmd.id);
                onClose();
              }}
              onMouseEnter={() => setSelectedIndex(idx)}
              className={cn(
                'flex w-full items-center justify-between rounded-lg px-2 py-2 text-left text-[length:var(--text-sm)] transition-colors',
                idx === selectedIndex ? 'bg-[var(--surface-2)] text-[var(--text)]' : 'text-[var(--text)] hover:bg-[var(--surface-2)]'
              )}
            >
              <div className="flex items-center gap-3">
                <span className="text-[var(--text-muted)]">{cmd.icon}</span>
                <span>{cmd.label}</span>
              </div>
              {cmd.shortcut && (
                <kbd className="rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">{cmd.shortcut}</kbd>
              )}
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="px-2 py-4 text-center text-[length:var(--text-sm)] text-[var(--text-muted)]">No commands found</div>
          )}
        </div>
      </div>
    </div>
  );
}
