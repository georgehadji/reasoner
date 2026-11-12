import { beforeEach, describe, expect, it } from 'vitest';
import type { User } from '@supabase/supabase-js';
import { selectAuthStatus, useAppStore } from './app-store';

/**
 * UI-8: `isAuthLoading` existed but nothing read it, so pages treated the
 * pre-INITIAL_SESSION `user === null` as "signed out". One derived status makes
 * the three states explicit and cannot disagree with the two fields it reads.
 */
const someUser = { id: 'u1' } as User;

describe('selectAuthStatus', () => {
  beforeEach(() => {
    useAppStore.setState({ user: null, isAuthenticated: false, isAuthLoading: true, sessionExpired: false });
  });

  it('is loading until the session has been read, even with no user', () => {
    expect(selectAuthStatus(useAppStore.getState())).toBe('loading');
  });

  it('is anonymous once loading ends with no user', () => {
    useAppStore.getState().setAuthLoading(false);
    expect(selectAuthStatus(useAppStore.getState())).toBe('anonymous');
  });

  it('is authenticated when a user is present', () => {
    useAppStore.getState().setUser(someUser);
    useAppStore.getState().setAuthLoading(false);
    expect(selectAuthStatus(useAppStore.getState())).toBe('authenticated');
  });

  it('markSessionExpired signs the user out locally as expired, logout as anonymous', () => {
    useAppStore.getState().setUser(someUser);
    useAppStore.getState().setAuthLoading(false);
    useAppStore.getState().markSessionExpired();
    expect(selectAuthStatus(useAppStore.getState())).toBe('expired');
    expect(useAppStore.getState().isAuthenticated).toBe(false);
    useAppStore.getState().logout();
    expect(selectAuthStatus(useAppStore.getState())).toBe('anonymous');
  });

  it('SM-U4: a 401 for an anonymous visitor does not become expired', () => {
    useAppStore.getState().setAuthLoading(false);
    useAppStore.getState().markSessionExpired();
    expect(selectAuthStatus(useAppStore.getState())).toBe('anonymous');
  });

  it('SM-U4: signing in again clears expired', () => {
    useAppStore.getState().setAuthLoading(false);
    useAppStore.getState().setUser(someUser);
    useAppStore.getState().markSessionExpired();
    useAppStore.getState().setUser(someUser);
    expect(selectAuthStatus(useAppStore.getState())).toBe('authenticated');
    expect(useAppStore.getState().isAuthenticated).toBe(true);
  });
});
