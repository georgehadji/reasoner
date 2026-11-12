import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { User as SupabaseUser } from '@supabase/supabase-js';
import { Conversation } from '@/lib/types';
import { STORAGE_KEYS, LIMITS } from '@/lib/config';
import { shallow } from 'zustand/shallow';
import type { SubscriptionStatus } from '@/hooks/useSubscription';
import { apiFetch } from '@/lib/api-client';
import { defineMachine } from '@/lib/state-machine';

export interface ComposerAttachment {
  id: string;
  file: File;
  name: string;
  size: number;
  type: string;
  previewUrl?: string;
}

export type Tier = 'budget' | 'premium';

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated' | 'expired';

/** SM-U4. `expired` = a request came back 401 while signed in; the guard sends the user to login. */
const AUTH = defineMachine<AuthStatus>('auth', {
  loading: ['anonymous', 'authenticated', 'expired'],
  anonymous: ['loading', 'authenticated'],
  authenticated: ['loading', 'anonymous', 'expired'],
  expired: ['loading', 'anonymous', 'authenticated'],
}, 'loading');

type AuthFields = Pick<AppState, 'isAuthLoading' | 'user' | 'sessionExpired'>;

/**
 * Derived, not stored: `user === null` alone cannot tell "signed out" from
 * "Supabase has not answered yet", and pages that guessed signed out redirected
 * on every reload (UI-8).
 */
export const selectAuthStatus = (s: AuthFields): AuthStatus =>
  s.isAuthLoading ? 'loading' : s.user ? 'authenticated' : s.sessionExpired ? 'expired' : 'anonymous';

/** The one auth writer: checks the move and keeps `isAuthenticated` equal to `!!user`. */
function authPatch(s: AuthFields, patch: Partial<AuthFields>) {
  const to = selectAuthStatus({ ...s, ...patch });
  const from = selectAuthStatus(s);
  if (from !== to) AUTH.move(from, to);
  return { ...patch, isAuthenticated: !!(patch.user !== undefined ? patch.user : s.user) };
}
export { shallow };

interface AppState {
  running: boolean;
  tier: Tier;
  isExpert: boolean;
  isImageMode: boolean;
  /** When true, skip the HyperGate method-confirmation picker and always auto-route. */
  autoMethodAlways: boolean;
  sidebarCollapsed: boolean;
  neuroPanelOpen: boolean;
  composerText: string;
  attachments: ComposerAttachment[];
  history: Conversation[];
  recentCommands: string[];

  // Auth
  user: SupabaseUser | null;
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  /** Set by a 401 while signed in; cleared by the next sign-in or an explicit logout. */
  sessionExpired: boolean;

  // Actions
  setRunning: (running: boolean) => void;
  toggleTier: () => void;
  toggleExpert: () => void;
  toggleImageMode: () => void;
  toggleAutoMethodAlways: () => void;
  toggleSidebar: () => void;
  toggleNeuroPanel: () => void;
  setComposerText: (text: string) => void;
  addAttachment: (file: File) => void;
  removeAttachment: (id: string) => void;
  clearAttachments: () => void;
  setHistory: (history: Conversation[]) => void;
  getAutoPreset: () => string;
  addRecentCommand: (id: string) => void;

  // Auth actions
  setUser: (user: SupabaseUser | null) => void;
  setAuthLoading: (loading: boolean) => void;
  logout: () => void;
  /** A request came back 401: the session is gone, so drop the local user. */
  markSessionExpired: () => void;

  // Subscription (shared cache — single fetch across all components)
  subscription: SubscriptionStatus | null;
  /** Id of the user `subscription` was fetched for; a different user must refetch. */
  subscriptionOwner: string | null;
  subscriptionLoading: boolean;
  subscriptionError: string | null;
  fetchSubscription: () => Promise<void>;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      running: false,
      tier: 'budget',
      isExpert: false,
      isImageMode: false,
      autoMethodAlways: false,
      sidebarCollapsed: false,
      neuroPanelOpen: false,
      composerText: '',
      attachments: [],
      history: [],
      recentCommands: [],

      // Auth defaults
      user: null,
      isAuthenticated: false,
      isAuthLoading: true,
      sessionExpired: false,

      // Subscription (shared — single fetch, not persisted)
      subscription: null,
      subscriptionOwner: null,
      subscriptionLoading: false,
      subscriptionError: null,

      setRunning: (running) => set({ running }),

      toggleTier: () =>
        set((state) => ({ tier: state.tier === 'budget' ? 'premium' : 'budget' })),

      toggleExpert: () => set((state) => ({ isExpert: !state.isExpert })),
      toggleImageMode: () => set((state) => ({ isImageMode: !state.isImageMode })),
      toggleAutoMethodAlways: () => set((state) => ({ autoMethodAlways: !state.autoMethodAlways })),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      toggleNeuroPanel: () => set((state) => ({ neuroPanelOpen: !state.neuroPanelOpen })),
      setComposerText: (composerText) => set({ composerText }),

      addAttachment: (file) =>
        set((state) => {
          if (state.attachments.length >= LIMITS.maxAttachments) return state;
          const id = `att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
          const attachment: ComposerAttachment = {
            id,
            file,
            name: file.name,
            size: file.size,
            type: file.type,
            previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
          };
          return { attachments: [...state.attachments, attachment] };
        }),

      removeAttachment: (id) =>
        set((state) => {
          const att = state.attachments.find((a) => a.id === id);
          if (att?.previewUrl) URL.revokeObjectURL(att.previewUrl);
          return { attachments: state.attachments.filter((a) => a.id !== id) };
        }),

      clearAttachments: () =>
        set((state) => {
          state.attachments.forEach((a) => {
            if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
          });
          return { attachments: [] };
        }),
      setHistory: (history) => set({ history }),
      addRecentCommand: (id) =>
        set((state) => {
          const next = [id, ...state.recentCommands.filter((c) => c !== id)].slice(0, LIMITS.maxRecentCommands);
          return { recentCommands: next };
        }),

      // Auth actions
      setUser: (user) =>
        set((s) => authPatch(s, { user, ...(user ? { sessionExpired: false } : {}) })),
      setAuthLoading: (loading) => set((s) => authPatch(s, { isAuthLoading: loading })),
      logout: () => set((s) => authPatch(s, { user: null, sessionExpired: false })),
      // Only a signed-in session can expire; a 401 for an anonymous visitor is just a 401.
      markSessionExpired: () =>
        set((s) => (s.user ? authPatch(s, { user: null, sessionExpired: true }) : s)),

      /** Returns the preset string to send to the API: "auto-budget" or "auto-premium". */
      getAutoPreset: () => `auto-${get().tier}`,

      // ── Subscription (shared cache — single fetch across all components) ──

      fetchSubscription: async () => {
        if (get().subscriptionLoading) return; // deduplicate concurrent fetches
        const owner = get().user?.id ?? null;
        // A plan cached for someone else must not show while this user's loads.
        const stale = get().subscriptionOwner !== owner;
        set({
          subscriptionLoading: true,
          subscriptionError: null,
          ...(stale ? { subscription: null } : {}),
        });
        try {
          const res = await apiFetch('/api/billing/subscription');
          if (res.ok) {
            const data: SubscriptionStatus = await res.json();
            set({ subscription: data, subscriptionOwner: owner, subscriptionLoading: false });
          } else {
            // Keep the last good plan: a failed load is not "free".
            set({ subscriptionLoading: false, subscriptionError: `Subscription request failed (${res.status})` });
          }
        } catch (err) {
          set({
            subscriptionLoading: false,
            subscriptionError: err instanceof Error ? err.message : 'Failed to fetch subscription',
          });
        }
      },
    }),
    {
      name: STORAGE_KEYS.appStore,
      version: 2,
      migrate: (persistedState) => {
        const s = (persistedState || {}) as Record<string, unknown>;
        return {
          tier: s.tier === 'premium' ? 'premium' : 'budget',
          isExpert: typeof s.isExpert === 'boolean' ? s.isExpert : false,
          sidebarCollapsed: typeof s.sidebarCollapsed === 'boolean' ? s.sidebarCollapsed : false,
          autoMethodAlways: typeof s.autoMethodAlways === 'boolean' ? s.autoMethodAlways : false,
          // Force image mode false on migration/load
          isImageMode: false,
          // Preserve recent commands across migrations (was previously dropped)
          recentCommands: Array.isArray(s.recentCommands) ? s.recentCommands : [],
        };
      },
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        tier: state.tier,
        isExpert: state.isExpert,
        sidebarCollapsed: state.sidebarCollapsed,
        recentCommands: state.recentCommands,
        autoMethodAlways: state.autoMethodAlways,
        // Do not persist isImageMode so it defaults to false on next load
        // Do NOT persist user/session — let Supabase handle that
      }),
    }
  )
);
