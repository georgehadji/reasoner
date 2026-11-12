'use client';

import { useRef, useCallback, useEffect, useState } from 'react';
import { PhaseEvent } from '@/lib/types';
import { API, WS } from '@/lib/config';
import { REASONER_WS_URL } from '@/lib/server-config';
import { fetchWithCsrf } from '@/lib/security-client';
import { defineMachine } from '@/lib/state-machine';

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';

/** SM-U2. `error` ends one connect(); a failure during a reconnect stays `reconnecting` until the retry budget is spent. */
const WS_MACHINE = defineMachine<ConnectionStatus>('ws.connection', {
  idle: ['connecting'],
  connecting: ['connected', 'reconnecting', 'disconnected', 'error', 'idle'],
  connected: ['connecting', 'reconnecting', 'disconnected', 'idle'],
  reconnecting: ['connecting', 'disconnected', 'error', 'idle'],
  disconnected: ['connecting', 'idle'],
  error: ['connecting', 'idle'],
}, 'idle');

export interface ConnectionInfo {
  status: ConnectionStatus;
  lastError: string | null;
}

type DoConnect = (pipelineId: string, onEvent: (ev: PhaseEvent) => void, isRetry?: boolean) => Promise<void>;

export function useWebSocketPipeline() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef = useRef<((ev: PhaseEvent) => void) | null>(null);
  const pipelineIdRef = useRef<string | null>(null);
  const doConnectRef = useRef<DoConnect>(undefined);
  /** Bumped by every connect, disconnect and unmount; an in-flight doConnect that sees a newer value stops. */
  const connectSeqRef = useRef(0);

  const [status, setStatus] = useState<ConnectionStatus>('idle');
  const statusRef = useRef<ConnectionStatus>('idle');
  const [lastError, setLastError] = useState<string | null>(null);
  const lastErrorRef = useRef<string | null>(null);

  /** The one status writer: every change goes through the machine; a no-op move is skipped. */
  const transition = useCallback((to: ConnectionStatus) => {
    if (statusRef.current === to) return;
    statusRef.current = WS_MACHINE.move(statusRef.current, to);
    setStatus(statusRef.current);
  }, []);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const setError = useCallback((msg: string | null) => {
    setLastError(msg);
    lastErrorRef.current = msg;
  }, []);

  /** Spends one retry: backoff, `reconnecting`, then connect again. False when the budget is gone. */
  const scheduleRetry = useCallback((pipelineId: string): boolean => {
    if (pipelineIdRef.current !== pipelineId || reconnectCountRef.current >= WS.maxReconnectAttempts) return false;
    reconnectCountRef.current += 1;
    const delay = WS.baseReconnectDelayMs * Math.pow(2, reconnectCountRef.current - 1);
    transition('reconnecting');
    console.debug(`[WebSocket] reconnecting in ${delay}ms (attempt ${reconnectCountRef.current})`);
    reconnectTimerRef.current = setTimeout(() => {
      if (onEventRef.current) doConnectRef.current?.(pipelineId, onEventRef.current, true);
    }, delay);
    return true;
  }, [transition]);

  const doConnect = useCallback<DoConnect>(async (pipelineId, onEvent, isRetry = false) => {
    clearReconnect();
    const seq = ++connectSeqRef.current;
    pipelineIdRef.current = pipelineId;
    onEventRef.current = onEvent;

    // One socket at a time: drop the old one before any await, and detach its
    // handlers so its late onclose cannot null the new socket or schedule a retry.
    if (wsRef.current) {
      const old = wsRef.current;
      wsRef.current = null;
      old.onclose = null;
      old.onmessage = null;
      old.onerror = null;
      old.close();
    }
    if (!isRetry) transition('connecting');

    // A failed attempt during a reconnect stays in the retry loop; only an
    // initial connect (or a spent budget) ends in `error`.
    const fail = (msg: string) => {
      setError(msg);
      if (isRetry && scheduleRetry(pipelineId)) return;
      transition('error');
    };

    // Pre-check: is the backend reachable?
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    try {
      const healthResp = await fetchWithCsrf('/api/health', { signal: controller.signal });
      clearTimeout(timeoutId);
      if (seq !== connectSeqRef.current) return;
      if (!healthResp.ok) {
        fail(`Backend returned ${healthResp.status} — cannot establish WebSocket`);
        return;
      }
    } catch {
      clearTimeout(timeoutId);
      if (seq !== connectSeqRef.current) return;
      fail(`Backend unreachable at ${REASONER_WS_URL} — is the server running?`);
      return;
    }

    transition('connecting');

    // A ticket, not a standing bearer token, travels with the handshake --
    // never in the query string (server access logs, browser history) and
    // single-use server-side, so a value visible in devtools network logs
    // can't be replayed. Fetched fresh on every connect/reconnect since
    // it's consumed on first use.
    let ticket: string;
    try {
      const ticketResp = await fetchWithCsrf(API.WEBSOCKET_TICKET, { method: 'POST' });
      if (seq !== connectSeqRef.current) return;
      if (!ticketResp.ok) {
        fail(`Could not obtain a connection ticket (${ticketResp.status})`);
        return;
      }
      ({ ticket } = await ticketResp.json());
    } catch {
      if (seq !== connectSeqRef.current) return;
      fail('Could not reach the backend to request a connection ticket');
      return;
    }
    if (seq !== connectSeqRef.current) return;

    const url = `${REASONER_WS_URL}?pipeline_id=${encodeURIComponent(pipelineId)}`;
    const ws = new WebSocket(url, [ticket]);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectCountRef.current = 0;
      setError(null);
      transition('connected');
      console.debug('[WebSocket] connected for pipeline:', pipelineId);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'event' && msg.data && onEventRef.current) {
          onEventRef.current(msg.data as PhaseEvent);
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      // Browser WebSocket error events are intentionally opaque (no detail exposed for security).
      // Diagnose the likely cause by checking backend health.
      const msg = lastErrorRef.current || 'WebSocket connection failed';
      console.error('[WebSocket] error:', msg);
    };

    ws.onclose = () => {
      // Superseded or deliberately closed: another connect owns the state now.
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      // Only attempt reconnect if we still care about this pipeline
      if (!scheduleRetry(pipelineId)) transition('disconnected');
    };
  }, [clearReconnect, scheduleRetry, setError, transition]);

  useEffect(() => {
    doConnectRef.current = doConnect;
  }, [doConnect]);

  const connect = useCallback(async (pipelineId: string, onEvent: (ev: PhaseEvent) => void) => {
    reconnectCountRef.current = 0;
    await doConnect(pipelineId, onEvent);
  }, [doConnect]);

  const disconnect = useCallback(() => {
    clearReconnect();
    connectSeqRef.current += 1;
    pipelineIdRef.current = null;
    onEventRef.current = null;
    reconnectCountRef.current = 0;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    transition('idle');
  }, [clearReconnect, transition]);

  const sendStop = useCallback((pipelineId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: 'stop', pipeline_id: pipelineId })
      );
    }
  }, []);

  useEffect(() => {
    return () => {
      clearReconnect();
      connectSeqRef.current += 1;
      // Null these BEFORE close(). close() fires onclose asynchronously, and
      // onclose reconnects whenever pipelineIdRef still matches the socket's
      // pipeline. Clearing the timer first is not enough: onclose runs after
      // this cleanup has finished and schedules a fresh timer into a ref
      // nobody will ever clear again, which then reconnects an unmounted hook
      // and setStates on it, up to WS.maxReconnectAttempts times.
      // disconnect() above already orders it this way; unmount did not.
      pipelineIdRef.current = null;
      onEventRef.current = null;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [clearReconnect]);

  return { connect, disconnect, sendStop, status, lastError };
}
