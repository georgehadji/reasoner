'use client';

import Link from 'next/link';
import { useId, useMemo, useState } from 'react';
import { CAPABILITIES } from '@/lib/capabilities.generated';

/**
 * The capabilities, set as a command menu scaled up until it is the section.
 * Typing filters, arrow keys and the pointer move the selection, Enter
 * follows the selected row's link. No keyboard shortcuts are shown: the
 * product has none for these, and a drawn one would be a false claim.
 *
 * Sources: api/mcp (MCP tools), api/routes/agent.py and sdk/typescript
 * (HTTP), main.py and reasoner.headless (CLI), api/streaming.py (SSE),
 * domain/preset_registry_western.py (Western-only), LICENSE + compose file
 * (self-hosting), the erasure route (erase_user_data).
 */
const COMMANDS = [
  { name: 'Ask from an agent', detail: 'An MCP server with six tools and one config block. Claude Desktop, Claude Code and most agent frameworks pick it up.', href: '/docs/mcp' },
  { name: 'Call it over HTTP', detail: 'One authenticated POST, or the TypeScript SDK. Take the result as JSON fields: claims, labels, open questions, a plan.', href: '/developers' },
  { name: 'Run it from a shell', detail: 'A command line for scripts and cron jobs, or the pipeline imported in-process with no server in between.', href: '/developers' },
  { name: 'Watch each phase land', detail: 'The run streams as server-sent events, one per phase, so a long run shows its working while it works.', href: '/how-it-works' },
  { name: 'Keep it Western-only', detail: 'Every preset has a twin that uses only US and EU models; the provider builder refuses any other.', href: '/#labs' },
  { name: 'Host it yourself', detail: 'Source-available under the Business Source License 1.1. The full stack runs from one Docker Compose file.', href: '/security' },
  { name: 'Erase what is stored', detail: 'One call deletes a user’s stored runs and data.', href: '/privacy' },
  { name: `Pick from ${CAPABILITIES.methods} methods`, detail: 'Debate, pre-mortem, Bayesian updating, Delphi and more. The method is chosen per question, or by you.', href: '/capabilities' },
] as const;

export function CommandList() {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const inputId = useId();
  const listId = useId();

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? COMMANDS.filter((c) => `${c.name} ${c.detail}`.toLowerCase().includes(q)) : COMMANDS;
  }, [query]);
  const sel = Math.min(selected, Math.max(rows.length - 1, 0));

  return (
    <section id="commands" aria-labelledby={`${inputId}-h`} className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
      <div data-ui data-reveal>
        <h2 id={`${inputId}-h`}>
          <label htmlFor={inputId} className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">
            What it does, by name
          </label>
        </h2>
        <input
          id={inputId}
          type="search"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={rows[sel] ? `${listId}-${sel}` : undefined}
          autoComplete="off"
          placeholder="Type to filter"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setSelected((s) => Math.min(s + 1, rows.length - 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setSelected((s) => Math.max(s - 1, 0));
            } else if (e.key === 'Enter' && rows[sel]) {
              e.preventDefault();
              window.location.assign(rows[sel].href);
            }
          }}
          className="mt-[var(--space-6)] h-[var(--space-16)] w-full rounded-[var(--site-radius)] bg-[var(--site-surface)] px-[var(--space-5)] text-[length:var(--site-lead)] text-[var(--site-ink)] placeholder:text-[var(--site-muted)] lg:w-5/6"
        />

        <ul id={listId} role="listbox" aria-label="Capabilities" className="mt-[var(--space-6)] list-none">
          {rows.map((c, i) => {
            const on = i === sel;
            return (
              <li
                key={c.name}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={on}
                onPointerEnter={() => setSelected(i)}
                onClick={() => setSelected(i)}
                className={`cursor-pointer rounded-[var(--site-radius)] px-[var(--space-5)] py-[var(--space-3)] transition-colors duration-[var(--dur-micro)] ${
                  on ? 'bg-[var(--site-accent)] text-[var(--site-accent-ink)]' : 'text-[var(--site-ink)]'
                }`}
              >
                <span className="block font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">{c.name}</span>
                {on && (
                  <span className="mt-[var(--space-2)] block max-w-[60ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
                    {c.detail}{' '}
                    <Link href={c.href} className="font-semibold underline underline-offset-4">
                      Read more<span className="sr-only">: {c.name}</span>
                    </Link>
                  </span>
                )}
              </li>
            );
          })}
          {rows.length === 0 && (
            <li className="px-[var(--space-5)] py-[var(--space-3)] text-[length:var(--site-body)] text-[var(--site-muted)]">
              Nothing matches. Try “agent”, “host” or “labs”.
            </li>
          )}
        </ul>
      </div>
    </section>
  );
}
