'use client';

import { useEffect } from 'react';
import { ThemeProvider } from 'next-themes';
import { supabase } from '@/lib/supabase';
import { useAppStore } from '@/stores/app-store';
import { clearLegacyHistory, deleteHistory, setHistoryOwner } from '@/lib/db';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <AuthProvider>{children}</AuthProvider>
    </ThemeProvider>
  );
}

function AuthProvider({ children }: { children: React.ReactNode }) {
  const setUser = useAppStore((s) => s.setUser);
  const setAuthLoading = useAppStore((s) => s.setAuthLoading);

  useEffect(() => {
    if (!supabase) {
      setAuthLoading(false);
      return;
    }

    // Register listener BEFORE any async calls so we don't miss the INITIAL_SESSION
    // event that fires after Supabase finishes processing the URL (including OAuth code exchange).
    // Decision Q9: the old shared history database has no owner; clear it.
    void clearLegacyHistory().catch(() => {});

    const { data: listener } = supabase.auth.onAuthStateChange((event, session) => {
      // Before setUser: the history hook reloads on the user change and must
      // already read this user's database (UI-5).
      setHistoryOwner(session?.user?.id ?? null);
      if (event === 'SIGNED_OUT') {
        // The next person on this browser starts with no cached plan and no
        // leftover anonymous history.
        useAppStore.setState({ subscription: null, history: [] });
        void deleteHistory(null).catch(() => {});
      }
      setUser(session?.user ?? null);
      if (event === 'INITIAL_SESSION') {
        setAuthLoading(false);
      }
    });

    return () => listener.subscription.unsubscribe();
  }, [setUser, setAuthLoading]);

  return <>{children}</>;
}
