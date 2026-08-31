'use client';

import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ShortcutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ShortcutModal({ isOpen, onClose }: ShortcutModalProps) {
  const shortcuts = [
    { keys: ['Enter'], label: 'Run pipeline' },
    { keys: ['Shift', 'Enter'], label: 'New line in composer' },
    { keys: ['Esc'], label: 'Stop running pipeline' },
    { keys: ['/'], label: 'Focus composer' },
    { keys: ['B'], label: 'Toggle sidebar' },
    { keys: ['Ctrl', 'K'], label: 'Command palette' },
    { keys: ['Ctrl', 'L'], label: 'Clear composer' },
    { keys: ['Ctrl', 'Shift', 'C'], label: 'Copy last response' },
    { keys: ['?'], label: 'Show this panel' },
  ];

  return (
    <div
      className={cn(
        'fixed inset-0 z-[300] flex items-center justify-center p-4 transition-all duration-[var(--dur-component)]',
        isOpen ? 'bg-[var(--scrim)] opacity-100' : 'bg-transparent opacity-0 pointer-events-none',
      )}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          'w-full max-w-[var(--width-form)] rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-lg)] transition-all duration-[var(--dur-component)]',
          isOpen ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-4 opacity-0 scale-95',
        )}
      >
        <div className="mb-4 flex items-center justify-between">
          <span className="text-[length:var(--text-base)] font-semibold text-[var(--text)]">Keyboard Shortcuts</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
            aria-label="Close shortcuts"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3 text-[length:var(--text-sm)]">
          {shortcuts.map((shortcut) => (
            <div key={shortcut.label} className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key, i) => (
                  <span key={key + i} className="flex items-center gap-1">
                    <kbd className="rounded bg-[var(--surface-2)] px-2 py-1 font-mono text-[var(--text-2)]">{key}</kbd>
                    {i < shortcut.keys.length - 1 && <span className="text-[var(--text-subtle)]">+</span>}
                  </span>
                ))}
              </div>
              <span className="text-[var(--text-muted)]">{shortcut.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
