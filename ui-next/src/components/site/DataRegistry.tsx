'use client';

import { useState, type ReactNode } from 'react';
import { USER_DATA_STORES } from '@/lib/user-data-stores';

/**
 * /privacy's hero. Left: the headline. Right (data-ui): every store that
 * holds an account's data, as the backend registry lists them, with a
 * switch that previews what each of the two erasure routes removes.
 * The live thing of the page: the visitor sees the difference between
 * erasing their data and closing their account before doing either.
 */
const MODES = [
  { id: 'kept', label: 'As stored', route: null },
  { id: 'data', label: 'Erase my data', route: 'DELETE /api/user/data' },
  { id: 'account', label: 'Delete my account', route: 'POST /api/account/delete' },
] as const;

type Mode = (typeof MODES)[number]['id'];

export function DataRegistry({ headline, lede }: { headline: ReactNode; lede: ReactNode }) {
  const [mode, setMode] = useState<Mode>('kept');
  const erased = (account?: boolean) => mode === 'account' || (mode === 'data' && !account);
  const count = USER_DATA_STORES.filter((s) => erased(s.account)).length;
  const route = MODES.find((m) => m.id === mode)?.route;

  return (
    <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
      <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
        {headline}
        <div className="site-after-headline">{lede}</div>
      </div>

      <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
        <figure
          data-ui
          className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
        >
          <div className="flex items-center justify-between gap-[var(--space-3)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
            <span className="font-semibold">Where one account&rsquo;s data lives</span>
            <span aria-live="polite" className="text-[var(--site-muted)] nums-tabular">
              {mode === 'kept' ? `${USER_DATA_STORES.length} stores` : `${count} of ${USER_DATA_STORES.length} erased`}
            </span>
          </div>

          <div
            role="group"
            aria-label="Preview an erasure"
            className="m-[var(--space-3)] flex flex-wrap rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]"
          >
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                aria-pressed={mode === m.id}
                onClick={() => setMode(m.id)}
                className="flex-1 whitespace-nowrap rounded-[var(--radius-sm)] px-[var(--space-3)] py-[var(--space-1)] text-[var(--site-muted)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--site-ink)] aria-pressed:bg-[var(--site-accent)] aria-pressed:font-semibold aria-pressed:text-[var(--site-accent-ink)]"
              >
                {m.label}
              </button>
            ))}
          </div>

          <ul className="list-none px-[var(--space-4)] pb-[var(--space-2)]">
            {USER_DATA_STORES.map((s) => {
              const gone = erased(s.account);
              return (
                <li
                  key={s.name}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-[var(--space-3)] border-t border-[var(--site-line)] py-[var(--space-1)]"
                >
                  <span className={`transition-opacity duration-[var(--dur-state)] ${gone ? 'text-[var(--site-muted)] line-through opacity-60' : ''}`}>
                    {s.label} <code className="font-mono text-[var(--site-muted)]">{s.name}</code>
                  </span>
                  <span className={gone ? 'font-semibold text-[var(--site-accent)]' : 'text-[var(--site-muted)]'}>
                    {gone ? 'Erased' : s.encrypted ? 'Encrypted' : s.account ? 'Account' : ''}
                  </span>
                </li>
              );
            })}
          </ul>

          <figcaption className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]">
            {route ? (
              <>
                Runs as <code className="font-mono text-[var(--site-ink)]">{route}</code>
                {mode === 'data' ? '; your profile and sign-in stay.' : '; also cancels billing.'}
              </>
            ) : (
              'Choose an erasure to see what it removes.'
            )}
          </figcaption>
        </figure>
      </div>
    </header>
  );
}
