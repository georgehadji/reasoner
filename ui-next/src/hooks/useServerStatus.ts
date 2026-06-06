'use client';

import { TIMING, API, LIMITS } from '@/lib/config';
import { useState, useEffect } from 'react';

export function useServerStatus() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    let interval: NodeJS.Timeout | undefined;
    let checkInFlight = false;

    async function check() {
      // Avoid overlapping checks when the backend is slow
      if (checkInFlight) return;
      checkInFlight = true;
      const controller = new AbortController();
      // Use a shorter timeout — if we get no response in 3s the backend is unresponsive
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      try {
        const resp = await fetch(API.HEALTH, { signal: controller.signal });
        if (mounted) setOnline(resp.ok);
      } catch {
        if (mounted) setOnline(false);
      } finally {
        clearTimeout(timeoutId);
        checkInFlight = false;
      }
    }

    function start() {
      // Guard against duplicate intervals if visibility toggles rapidly
      if (interval) {
        clearInterval(interval);
      }
      check();
      interval = setInterval(check, TIMING.serverStatusCheckIntervalMs);
    }

    function stop() {
      clearInterval(interval);
      interval = undefined;
    }

    start();
    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        start();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      mounted = false;
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return online;
}
