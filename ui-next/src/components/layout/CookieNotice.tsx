'use client';

import { useSyncExternalStore } from 'react';
import Link from 'next/link';

/**
 * Cookie notice.
 *
 * Reasoner sets auth (Supabase session) and CSRF cookies, but shipped no notice
 * of any kind, and nothing linked to the Cookie Policy that already existed.
 *
 * Deliberately a *notice*, not a consent gate: every cookie this app sets is
 * strictly necessary — you cannot sign in or submit a form without them — and
 * strictly necessary cookies do not require prior consent under the ePrivacy
 * Directive or GDPR. There is no analytics or advertising cookie to opt out of.
 * If you later add product analytics, this must become a real consent gate that
 * blocks those cookies until the user accepts.
 */
const STORAGE_KEY = 'reasoner.cookie-notice.acknowledged';

// Reading localStorage is reading state that lives outside React, so this uses
// useSyncExternalStore rather than an effect that calls setState. The effect
// version renders once, then immediately re-renders — which is both a cascading
// render and a visible flash of the banner on every load for users who already
// dismissed it.
const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  // Keep multiple tabs in agreement.
  window.addEventListener('storage', onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener('storage', onChange);
  };
}

function isAcknowledged() {
  try {
    return Boolean(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    // Private browsing or storage disabled: show the notice. Dismissing just
    // won't persist, which is better than suppressing it entirely.
    return false;
  }
}

// On the server there is no localStorage. Report "acknowledged" so the banner
// is absent from the SSR output and appears only once the client confirms it is
// actually needed — the alternative renders it server-side and rips it away.
const serverSnapshot = () => true;

function acknowledge() {
  try {
    window.localStorage.setItem(STORAGE_KEY, new Date().toISOString());
  } catch {
    /* nothing to do; the notice stays dismissed for this page view */
  }
  listeners.forEach((notify) => notify());
}

export function CookieNotice() {
  const acknowledged = useSyncExternalStore(subscribe, isAcknowledged, serverSnapshot);

  if (acknowledged) return null;

  return (
    <div
      role="region"
      aria-label="Cookie notice"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur px-4 py-4 shadow-lg"
    >
      <div className="mx-auto flex max-w-4xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm leading-relaxed text-[var(--text-2)]">
          We use only the cookies needed to keep you signed in and to protect forms against
          cross-site request forgery. No advertising or tracking cookies.{' '}
          <Link href="/cookies" className="text-[var(--accent)] hover:underline">
            Read the cookie policy
          </Link>
          .
        </p>
        <button
          onClick={acknowledge}
          className="shrink-0 rounded-lg bg-[var(--accent)] px-5 py-2 text-sm font-medium text-[var(--accent-text)] transition-opacity hover:opacity-90"
        >
          Got it
        </button>
      </div>
    </div>
  );
}
