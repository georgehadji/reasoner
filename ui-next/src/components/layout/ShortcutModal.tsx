'use client';

import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

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

  /* A modal <dialog> traps Tab, closes on Escape and returns focus to whatever
     opened it. Same pattern as SiteHeader's drawer and ChatFeed's lightbox. */
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (isOpen && !el.open) el.showModal();
    if (!isOpen && el.open) el.close();
  }, [isOpen]);

  return (
    // No `display` utility on the <dialog>: it would override the UA's display:none while closed.
    <dialog
      ref={dialogRef}
      aria-labelledby="shortcuts-title"
      onClose={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="m-0 h-full max-h-none w-full max-w-none border-0 bg-[var(--scrim)] p-0 text-[var(--text)]"
    >
      <div
        className="flex h-full items-center justify-center p-[var(--space-4)]"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      >
        <div className="animate-phase-reveal w-full max-w-[var(--width-form)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-6)] shadow-[var(--shadow-lg)]">
          <div className="mb-[var(--space-4)] flex items-center justify-between">
            <h2 id="shortcuts-title" className="text-[length:var(--text-base)] font-semibold text-[var(--text)]">
              Keyboard Shortcuts
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="-mr-[var(--space-3)] flex h-11 w-11 items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
              aria-label="Close shortcuts"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <dl className="space-y-[var(--space-3)] text-[length:var(--text-sm)]">
            {shortcuts.map((shortcut) => (
              <div key={shortcut.label} className="flex items-center justify-between gap-[var(--space-4)]">
                <dt className="flex items-center gap-[var(--space-1)]">
                  {shortcut.keys.map((key, i) => (
                    <span key={key + i} className="flex items-center gap-[var(--space-1)]">
                      <kbd className="rounded-[var(--radius-sm)] bg-[var(--surface-2)] px-[var(--space-2)] py-[var(--space-1)] font-mono text-[var(--text-2)]">{key}</kbd>
                      {i < shortcut.keys.length - 1 && <span className="text-[var(--text-subtle)]" aria-hidden="true">+</span>}
                    </span>
                  ))}
                </dt>
                <dd className="text-right text-[var(--text-muted)]">{shortcut.label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </dialog>
  );
}
