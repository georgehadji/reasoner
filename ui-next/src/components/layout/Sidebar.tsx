'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAppStore } from '@/stores/app-store';
import { Conversation } from '@/lib/types';
import {
  Plus,
  PanelLeft,
  Trash2,
  Brain,
  History,
  Play,
  Search,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Loader2,
} from 'lucide-react';
import { NeuroPanel } from './NeuroPanel';
import { Tooltip } from '@/components/ui/Tooltip';
import { API, LIMITS, PIPELINE_DEFAULTS } from '@/lib/config';
import { cn } from '@/lib/utils';

interface SidebarProps {
  conversations: Conversation[];
  onLoad: (conv: Conversation) => void;
  onDelete: (id: string) => void;
  onClear: () => void;
  onNew: () => void;
  onResume?: (pipelineId: string) => void;
  conversationId?: string | null;
  lastUserPrompt?: string;
  lastAssistantResponse?: string;
}

function formatDateGroup(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const isSameDay = (a: Date, g: Date) =>
    a.getFullYear() === g.getFullYear() &&
    a.getMonth() === g.getMonth() &&
    a.getDate() === g.getDate();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const startOfWeek = new Date(now);
  startOfWeek.setDate(now.getDate() - now.getDay());
  if (isSameDay(date, now)) return 'Today';
  if (isSameDay(date, yesterday)) return 'Yesterday';
  if (date >= startOfWeek) return 'This week';
  return 'Older';
}

function MemoryStatus() {
  // 'loading' is distinct from 'unknown': the old initial value was 'unknown',
  // which renders red "Memory unavailable", so every page load flashed a
  // failure state until /neuro/health resolved.
  const [status, setStatus] = useState<'loading' | 'ok' | 'degraded' | 'unknown'>('loading');
  useEffect(() => {
    let mounted = true;
    fetch(API.NEURO_HEALTH)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => { if (mounted) setStatus(d.status === 'ok' ? 'ok' : 'degraded'); })
      .catch(() => { if (mounted) setStatus('unknown'); });
    return () => { mounted = false; };
  }, []);

  /* Shape carries the state as well as hue: a coloured dot alone is invisible
     to a red/green-blind user and to a monochrome print. */
  const { StatusIcon, statusTone, statusLabel } =
    status === 'ok'
      ? { StatusIcon: CheckCircle2, statusTone: 'text-[var(--ok)]', statusLabel: 'Memory healthy' }
      : status === 'degraded'
      ? { StatusIcon: AlertTriangle, statusTone: 'text-[var(--warn)]', statusLabel: 'Memory degraded' }
      : status === 'loading'
      ? { StatusIcon: Loader2, statusTone: 'text-[var(--text-subtle)]', statusLabel: 'Checking memory…' }
      : { StatusIcon: HelpCircle, statusTone: 'text-[var(--red)]', statusLabel: 'Memory unavailable' };

  return (
    <Tooltip text={statusLabel}>
      <div className="flex cursor-default items-center gap-2 rounded-[var(--radius)] px-2 py-1.5 text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
        <Brain className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Memory</span>
        <StatusIcon className={cn('ml-auto h-3.5 w-3.5', statusTone)} aria-hidden="true" />
        <span className="sr-only">{statusLabel}</span>
      </div>
    </Tooltip>
  );
}

function SidebarComponent({
  conversations,
  onLoad,
  onDelete,
  onClear,
  onNew,
  onResume,
  conversationId,
  lastUserPrompt,
  lastAssistantResponse,
}: SidebarProps) {
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const neuroPanelOpen = useAppStore((s) => s.neuroPanelOpen);
  const toggleNeuroPanel = useAppStore((s) => s.toggleNeuroPanel);
  const [query, setQuery] = useState('');
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const asideRef = useRef<HTMLElement>(null);
  const floatingRef = useRef<HTMLButtonElement>(null);
  const wasCollapsed = useRef(collapsed);

  /* Below `sm` the sidebar is a modal drawer over the conversation, so it has
     to behave like one: trap Tab, close on Escape, give focus back to whatever
     opened it. Above `sm` it is a static panel and none of that applies —
     hence the media query rather than a blanket trap.
     Capture phase + stopPropagation so Escape closes the drawer and does NOT
     also reach the global shortcut handler, which reads Escape as "stop the
     running pipeline".
     ponytail: the breakpoint is read once per open, not on resize — a resize
     mid-drawer is a device rotation away, and the backdrop still closes on tap. */
  useEffect(() => {
    const justOpened = wasCollapsed.current && !collapsed;
    wasCollapsed.current = collapsed;

    if (collapsed) return;
    if (!window.matchMedia('(max-width: 639px)').matches) return;

    const root = asideRef.current;
    const focusable = () =>
      Array.from(
        root?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => el.offsetWidth > 0 || el.offsetHeight > 0);

    // Only pull focus when the drawer was actually opened — never on page load.
    if (justOpened) focusable()[0]?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        toggleSidebar();
        return;
      }
      if (e.key !== 'Tab') return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [collapsed, toggleSidebar]);

  /* Focus restore, on the CLOSE commit rather than the open effect's cleanup.
     The previous version snapshotted `document.activeElement` inside the open
     effect — but the only thing that opens the drawer on mobile is the
     floating toggle, which is rendered `{collapsed && …}`. React unmounts it
     before that effect runs, so the snapshot was already <body> and the
     restore was a no-op on the one path it existed for. Here the toggle has
     been re-mounted by the time this runs, so there is something to focus. */
  const wasOpen = useRef(!collapsed);
  useEffect(() => {
    // Its own ref, not `wasCollapsed`: the trap effect above already writes
    // that one and runs first, so reading it here would always compare equal.
    const justClosed = wasOpen.current && collapsed;
    wasOpen.current = !collapsed;
    if (!justClosed) return;
    if (!window.matchMedia('(max-width: 639px)').matches) return;
    floatingRef.current?.focus();
  }, [collapsed]);

  const methodTags = useMemo(
    () => Array.from(new Set(conversations.map((c) => c.method).filter(Boolean))),
    [conversations],
  );

  const filtered = useMemo(() => {
    const latestByThread = new Map<string, Conversation>();
    conversations.forEach((c) => {
      const key = c.conversation_id || c.id;
      const existing = latestByThread.get(key);
      if (!existing || new Date(c.timestamp) > new Date(existing.timestamp)) {
        latestByThread.set(key, c);
      }
    });
    return Array.from(latestByThread.values()).filter((c) => {
      const matchesQuery = !query.trim() || c.problem.toLowerCase().includes(query.toLowerCase());
      const matchesTag = !activeTag || c.method === activeTag || c.preset === activeTag;
      return matchesQuery && matchesTag;
    });
  }, [conversations, query, activeTag]);

  const grouped = useMemo(() => {
    const map = new Map<string, Conversation[]>();
    filtered.forEach((c) => {
      const g = formatDateGroup(c.timestamp);
      if (!map.has(g)) map.set(g, []);
      map.get(g)!.push(c);
    });
    return ['Today', 'Yesterday', 'This week', 'Older']
      .filter((g) => map.has(g))
      .map((g) => ({ group: g, items: map.get(g)! }));
  }, [filtered]);

  return (
    <>
      {/* Mobile backdrop */}
      {!collapsed && (
        <div
          className="fixed inset-0 z-40 bg-[var(--scrim)] backdrop-blur-sm sm:hidden"
          onClick={toggleSidebar}
          aria-hidden="true"
        />
      )}

      <aside
        ref={asideRef}
        id="app-sidebar"
        aria-label="Conversations"
        /* Collapsed is `w-0 overflow-hidden`, which hides the panel visually but
           leaves every control in the tag order — Tag walked through an invisible
           sidebar. `inert` takes the whole subtree out of focus and a11y. */
        inert={collapsed}
        className={cn(
          'fixed left-0 top-0 z-50 flex h-full flex-col bg-[var(--sidebar-bg)] transition-[width] duration-[var(--dur-scene)] ease-[var(--ease-entrance)] sm:static',
          collapsed ? 'w-0 overflow-hidden' : 'w-[272px]',
        )}
      >
        {/* Header — the rail owns its own ground, so nothing here needs a
            border or a filled button to separate itself from the page. */}
        <div className="flex items-center justify-between gap-1 px-2 pb-1 pt-2">
          <Tooltip text="Collapse sidebar">
            <button
              type="button"
              onClick={toggleSidebar}
              className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--text)]"
              aria-label="Collapse sidebar"
              aria-expanded={!collapsed}
              aria-controls="app-sidebar"
            >
              <PanelLeft className="h-4 w-4" aria-hidden="true" />
            </button>
          </Tooltip>
        </div>

        <div className="px-2 pb-2">
          <button
            type="button"
            onClick={onNew}
            className="flex h-10 w-full cursor-pointer items-center gap-2 rounded-[var(--radius)] px-2 text-left text-[length:var(--text-sm)] font-medium leading-[var(--lh-ui)] text-[var(--accent)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--sidebar-hover)]"
          >
            <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
            New problem
          </button>

          {/* History / Memory: two peer views of the rail, so they read as a
              segmented control rather than two more buttons in a stack. */}
          <div className="mt-1 flex gap-0.5 rounded-[var(--radius)] bg-[var(--sidebar-hover)] p-0.5">
            <button
              type="button"
              onClick={() => neuroPanelOpen && toggleNeuroPanel()}
              aria-pressed={!neuroPanelOpen}
              className={cn(
                'flex h-9 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-[var(--radius-sm)] px-2 text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] transition-colors duration-[var(--dur-state)] ease-[var(--ease-standard)]',
                !neuroPanelOpen
                  ? 'bg-[var(--surface)] text-[var(--text)] shadow-[var(--shadow)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)]',
              )}
            >
              <History className="h-3.5 w-3.5" aria-hidden="true" />
              History
            </button>
            <button
              type="button"
              onClick={() => !neuroPanelOpen && toggleNeuroPanel()}
              aria-pressed={neuroPanelOpen}
              className={cn(
                'flex h-9 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-[var(--radius-sm)] px-2 text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] transition-colors duration-[var(--dur-state)] ease-[var(--ease-standard)]',
                neuroPanelOpen
                  ? 'bg-[var(--surface)] text-[var(--text)] shadow-[var(--shadow)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)]',
              )}
            >
              <Brain className="h-3.5 w-3.5" aria-hidden="true" />
              Memory
            </button>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-2 pb-2 scrollbar-thin">
          {neuroPanelOpen ? (
            <NeuroPanel
              conversationId={conversationId}
              lastUserPrompt={lastUserPrompt}
              lastAssistantResponse={lastAssistantResponse}
            />
          ) : (
            <>
              {/* Search */}
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" aria-hidden="true" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search conversations…"
                  aria-label="Search conversations"
                  className="input-smooth h-10 w-full rounded-[var(--radius)] border border-transparent bg-[var(--sidebar-field)] pl-9 pr-3 text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text)] placeholder:text-[var(--text-muted)] focus:border-[var(--border-strong)]"
                />
              </div>

              {/* Method filter tags */}
              {methodTags.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {activeTag && (
                    <button
                      type="button"
                      onClick={() => setActiveTag(null)}
                      className="flex h-10 cursor-pointer items-center rounded-[var(--radius-pill)] px-3 text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--text)]"
                    >
                      Clear ×
                    </button>
                  )}
                  {methodTags.slice(0, LIMITS.maxTagDisplay).map((tag) => (
                    <button
                      key={String(tag)}
                      type="button"
                      onClick={() => setActiveTag(tag === activeTag ? null : tag ?? null)}
                      aria-pressed={activeTag === tag}
                      className={cn(
                        'flex h-10 cursor-pointer items-center rounded-[var(--radius-pill)] px-3 text-[length:var(--text-xs)] leading-[var(--lh-ui)] font-medium transition-colors duration-[var(--dur-state)] ease-[var(--ease-standard)]',
                        activeTag === tag
                          ? 'bg-[var(--accent)] text-[var(--accent-text)]'
                          : 'bg-[var(--sidebar-hover)] text-[var(--text-muted)] hover:bg-[var(--sidebar-active)] hover:text-[var(--text)]',
                      )}
                    >
                      {String(tag).replace(/_/g, '-')}
                    </button>
                  ))}
                </div>
              )}

              {/* Empty state */}
              {filtered.length === 0 && (
                <div className="flex flex-col items-center gap-2 py-12 text-center">
                  <History className="h-8 w-8 text-[var(--text-subtle)]" aria-hidden="true" />
                  <p className="text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">No conversations yet</p>
                  {/* --text-subtle measures 4.29:1 on --sidebar-bg (it clears
                      4.7:1 only on the lighter --bg), so this rail steps up
                      one level rather than reusing the page's quietest tone. */}
                  <p className="text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]">Start reasoning to see history here</p>
                </div>
              )}

              {/* Grouped list */}
              <div className="flex flex-col gap-5">
                {grouped.map(({ group, items }) => (
                  <div key={group}>
                    <div className="mb-1 px-2 text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] text-[var(--text-muted)]">
                      {group}
                    </div>
                    <div className="flex flex-col gap-0.5">
                      {items.map((conv) => {
                        const title =
                          conv.problem.length > LIMITS.titleTruncateChars
                            ? conv.problem.slice(0, LIMITS.titleTruncateChars) + '…'
                            : conv.problem;
                        const isCurrent =
                          !!conversationId &&
                          (conv.conversation_id === conversationId || conv.id === conversationId);
                        return (
                          /* The row used to be role="button" with two real
                             buttons inside it. `button` has presentational
                             children in ARIA, so Resume and Delete were
                             stripped from the a11y tree entirely. A plain
                             container with a real button for the title fixes
                             that and hands back native Enter/Space, so the
                             hand-rolled onKeyDown and both stopPropagation
                             calls go away with it. */
                          <div
                            key={conv.id}
                            className={cn(
                              'group relative flex items-center rounded-[var(--radius)]',
                              'transition-colors duration-[var(--dur-state)] ease-[var(--ease-standard)]',
                              isCurrent
                                ? 'bg-[var(--sidebar-active)]'
                                : 'hover:bg-[var(--sidebar-hover)]',
                            )}
                          >
                            {/* `title` rather than <Tooltip>: Tooltip wraps its
                                children in a focusable span, which on a real
                                button is a duplicate tab stop — three per row.
                                The native tooltip also renders in the top
                                layer, so it is not clipped by this scroller.
                                aria-label carries the untruncated problem and
                                still contains the visible text (WCAG 2.5.3). */}
                            <button
                              type="button"
                              onClick={() => onLoad(conv)}
                              aria-current={isCurrent ? 'true' : undefined}
                              aria-label={conv.problem}
                              title={conv.problem}
                              className={cn(
                                'flex h-10 w-full cursor-pointer items-center rounded-[var(--radius)] px-2 text-left',
                                'text-[length:var(--text-sm)] leading-[var(--lh-ui)]',
                                isCurrent
                                  ? 'font-medium text-[var(--text)]'
                                  : 'text-[var(--text-2)] group-hover:text-[var(--text)]',
                              )}
                            >
                              <span className="truncate">{title}</span>
                            </button>

                            {/* Actions float over the row's tail rather than
                                taking layout width, so the title measures the
                                same hovered or not — as a flex sibling it made
                                every title re-truncate on hover. */}
                            <div
                              className={cn(
                                'pointer-events-none absolute inset-y-0 right-0 flex items-center rounded-r-[var(--radius)] pl-2 opacity-0',
                                'transition-opacity duration-[var(--dur-micro)] ease-[var(--ease-standard)]',
                                'focus-within:pointer-events-auto focus-within:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100',
                                isCurrent ? 'bg-[var(--sidebar-active)]' : 'bg-[var(--sidebar-hover)]',
                              )}
                            >
                              {onResume && conv.pipeline_id && conv.kind === 'pipeline' && (
                                <button
                                  type="button"
                                  onClick={() => onResume(conv.pipeline_id!)}
                                  title="Resume pipeline"
                                  className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:text-[var(--accent)]"
                                  aria-label={`Resume pipeline for "${title}"`}
                                >
                                  <Play className="h-4 w-4" aria-hidden="true" />
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => onDelete(conv.id)}
                                title="Delete conversation"
                                className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:text-[var(--red)]"
                                aria-label={`Delete conversation "${title}"`}
                              >
                                <Trash2 className="h-4 w-4" aria-hidden="true" />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-[var(--border)] p-2">
          <MemoryStatus />
          <button
            type="button"
            onClick={onClear}
            className="mt-0.5 flex h-10 w-full cursor-pointer items-center rounded-[var(--radius)] px-2 text-left text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--text)]"
          >
            Clear cache
          </button>
        </div>
      </aside>

      {/* Floating toggle when collapsed */}
      {collapsed && (
        <button
          ref={floatingRef}
          type="button"
          onClick={toggleSidebar}
          aria-label="Open sidebar"
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          title="Open sidebar"
          /* Was `hidden sm:flex`, which left phone users with no way to
             reopen the drawer once closed. Mid-edge on mobile so it clears
             the chat header and the composer; back to top-left at sm+. */
          className="fixed left-3 top-1/2 z-50 flex h-11 w-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] shadow-[var(--shadow)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:border-[var(--border-strong)] hover:bg-[var(--surface-2)] hover:text-[var(--text)] sm:top-3 sm:translate-y-0"
        >
          <PanelLeft className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </>
  );
}

export const Sidebar = React.memo(SidebarComponent, (prev, next) => {
  return (
    prev.conversations.length === next.conversations.length &&
    prev.conversationId === next.conversationId &&
    prev.lastUserPrompt === next.lastUserPrompt &&
    prev.lastAssistantResponse === next.lastAssistantResponse
  );
});
