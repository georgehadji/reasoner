'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { stopPipeline } from '@/lib/api-client';

/**
 * One run, captured when it starts. Its handlers read from the ticket, never
 * from page refs that New or Load can move while the run is still streaming.
 */
export interface RunTicket {
  /** Every stream of this run (run, follow-up, resume) listens to this signal. */
  abort: AbortController;
  /** Set once the id exists (after the gate check). stop() sends it to the server. */
  clientRunId: string | null;
  /** The thread this run saves into, fixed once at start. */
  conversationId: string | null;
}

/**
 * Owns the run lifecycle (docs/plans/audit-remediation-2-2026-10-20.md PR 9).
 *
 * - UI-2: begin() returns null while a run (or its gate check) is active, so a
 *   second Enter cannot start a second run. A ref, not state: two key presses
 *   in one tick both read the same stale state.
 * - UI-1: stop() aborts the ticket's signal, which every stream receives, so a
 *   resumed run stops too instead of streaming on while billed.
 * - UI-3: the ticket carries the conversation id the run belongs to.
 * - UI-4: stop() posts `/api/stop?run_id=...`. A bare `/api/stop` is the
 *   admin "stop every user's run" call, and for anyone else a swallowed 403.
 */
export function useRunController(sendWsStop: (runId: string) => void) {
  const ticketRef = useRef<RunTicket | null>(null);
  const sendWsStopRef = useRef(sendWsStop);
  useEffect(() => {
    sendWsStopRef.current = sendWsStop;
  }, [sendWsStop]);

  const begin = useCallback((): RunTicket | null => {
    if (ticketRef.current) return null;
    const ticket: RunTicket = { abort: new AbortController(), clientRunId: null, conversationId: null };
    ticketRef.current = ticket;
    return ticket;
  }, []);

  /** Ends a run that finished on its own. A no-op for a ticket stop() already ended. */
  const finish = useCallback((ticket: RunTicket) => {
    if (ticketRef.current === ticket) ticketRef.current = null;
  }, []);

  const stop = useCallback(() => {
    const ticket = ticketRef.current;
    if (!ticket) return;
    ticketRef.current = null;
    ticket.abort.abort();
    if (ticket.clientRunId) {
      sendWsStopRef.current(ticket.clientRunId);
      void stopPipeline(ticket.clientRunId);
    }
  }, []);

  const isActive = useCallback(() => ticketRef.current !== null, []);

  // Leaving the page stops the run rather than leaving it streaming unseen.
  useEffect(() => stop, [stop]);

  return useMemo(() => ({ begin, finish, stop, isActive }), [begin, finish, stop, isActive]);
}
