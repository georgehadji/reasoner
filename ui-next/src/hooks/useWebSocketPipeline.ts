'use client';

import { useRef, useCallback, useEffect, useState } from 'react';
import { PhaseEvent } from '@/lib/types';
import { WS } from '@/lib/config';
import { REASONER_WS_URL } from '@/lib/server-config';
import { getAuthToken } from '@/lib/auth';
import { fetchWithCsrf } from '@/lib/security-client';

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'error';

export interface ConnectionInfo {
  status: ConnectionStatus;
  lastError: string | null;
}

export function useWebSocketPipeline() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef = useRef<((ev: PhaseEvent) => void) | null>(null);
  const pipelineIdRef = useRef<string | null>(null);
  const doConnectRef = useRef<(pipelineId: string, onEvent: (ev: PhaseEvent) => void) => void>(undefined);

  const [status, setStatus] = useState<ConnectionStatus>('idle');
  const [lastError, setLastError] = useState<string | null>(null);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const lastErrorRef = useRef<string | null>(null);

  const doConnect = useCallback(async (pipelineId: string, onEvent: (ev: PhaseEvent) => void) => {
    clearReconnect();
    pipelineIdRef.current = pipelineId;
    onEventRef.current = onEvent;

    // Pre-check: is the backend reachable?
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    try {
      const healthResp = await fetchWithCsrf('/api/health', { signal: controller.signal });
      if (!healthResp.ok) {
        const msg = `Backend returned ${healthResp.status} — cannot establish WebSocket`;
        setLastError(msg);
        lastErrorRef.current = msg;
        setStatus('error');
        clearTimeout(timeoutId);
        return;
      }
    } catch {
      const msg = `Backend unreachable at ${REASONER_WS_URL} — is the server running?`;
      setLastError(msg);
      lastErrorRef.current = msg;
      setStatus('error');
      clearTimeout(timeoutId);
      return;
    }
    clearTimeout(timeoutId);
    setLastError(null);
    lastErrorRef.current = null;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus('connecting');
    const token = await getAuthToken();
    let url = `${REASONER_WS_URL}?pipeline_id=${encodeURIComponent(pipelineId)}`;
    if (token) {
      url += `&token=${encodeURIComponent(token)}`;
    }
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectCountRef.current = 0;
      setStatus('connected');
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
      wsRef.current = null;
      const currentPipelineId = pipelineIdRef.current;

      // Only attempt reconnect if we still care about this pipeline
      if (currentPipelineId === pipelineId && reconnectCountRef.current < WS.maxReconnectAttempts) {
        reconnectCountRef.current += 1;
        const delay = WS.baseReconnectDelayMs * Math.pow(2, reconnectCountRef.current - 1);
        setStatus('reconnecting');
        console.debug(`[WebSocket] reconnecting in ${delay}ms (attempt ${reconnectCountRef.current})`);
        reconnectTimerRef.current = setTimeout(() => {
          if (onEventRef.current) doConnectRef.current?.(pipelineId, onEventRef.current);
        }, delay);
      } else {
        setStatus('disconnected');
      }
    };
  }, [clearReconnect]);

  useEffect(() => {
    doConnectRef.current = doConnect;
  }, [doConnect]);

  const connect = useCallback(async (pipelineId: string, onEvent: (ev: PhaseEvent) => void) => {
    reconnectCountRef.current = 0;
    await doConnect(pipelineId, onEvent);
  }, [doConnect]);

  const disconnect = useCallback(() => {
    clearReconnect();
    pipelineIdRef.current = null;
    onEventRef.current = null;
    reconnectCountRef.current = 0;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('idle');
  }, [clearReconnect]);

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
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [clearReconnect]);

  return { connect, disconnect, sendStop, status, lastError };
}
