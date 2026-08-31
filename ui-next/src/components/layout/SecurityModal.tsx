'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Lock, ShieldCheck, Database, Server, Users, History, Globe, X } from 'lucide-react';
import { cn } from '@/lib/utils';

export function SecurityModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  // Unmount when closed. `opacity-0 + pointer-events-none` hides it from sight
  // only: the subtree stayed in the accessibility tree, so its 13 headings ran
  // ahead of the page's own <h1> in the outline, and its close button was still
  // tabbable — keyboard users landed inside an invisible dialog. SiteHeader and
  // SiteFooter each render one, so both effects happened twice per page.
  if (!isOpen) return null;
  // Never reached during SSR while `isOpen` starts false, but the guard keeps
  // that an implementation detail rather than a load-bearing assumption.
  if (typeof document === 'undefined') return null;

  // Portalled to <body>. `position: fixed` resolves against the nearest ancestor
  // carrying a filter, backdrop-filter or transform — not the viewport — and
  // this renders inside SiteHeader, which is `backdrop-blur-xl`. The overlay was
  // laid out against the 64px header bar: measured 1265×64 on a 1280×800
  // viewport. Inside the mobile drawer it was worse, clipped to that panel's
  // 319px column by the panel's reveal transform.
  return createPortal(
    <div
      className={cn(
        'fixed inset-0 z-[300] flex items-center justify-center p-4 transition-all duration-[var(--dur-component)]',
        isOpen ? 'bg-[var(--scrim)] opacity-100' : 'bg-transparent opacity-0 pointer-events-none',
      )}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          'w-full max-w-[var(--width-content)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-8 shadow-[var(--shadow-lg)] transition-all duration-[var(--dur-component)]',
          isOpen ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-4 opacity-0 scale-95',
        )}
      >
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--surface-2)] text-[var(--text)]">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-[length:var(--text-lg)] font-bold text-[var(--text)]">Enterprise Security & Trust</h3>
              <p className="text-[length:var(--text-sm)] text-[var(--text-2)]">Advanced safeguards for mission-critical reasoning.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close security details"
            className="min-touch rounded-[var(--radius)] p-2 text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Column 1 */}
          <div className="space-y-6">
            <section className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--surface-2)] text-[var(--text-2)]">
                <Lock className="h-5 w-5" />
              </div>
              <div>
                <h4 className="font-semibold text-[var(--text-2)] mb-1 uppercase tracking-wider text-[length:var(--text-2xs)]">Compliance</h4>
                <h5 className="font-bold text-[var(--text)] text-[length:var(--text-sm)] mb-1">SOC 2 Type II — Roadmap</h5>
                <p className="text-[length:var(--text-xs)] text-[var(--text-2)] leading-relaxed">
                  Not yet certified. See our <a href="/security" className="underline hover:text-[var(--text)]">security page</a> for current controls and audit history.
                </p>
              </div>
            </section>

            <section className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--surface-2)] text-[var(--text-2)]">
                <Database className="h-5 w-5" />
              </div>
              <div>
                <h4 className="font-semibold text-[var(--text-2)] mb-1 uppercase tracking-wider text-[length:var(--text-2xs)]">Data Privacy</h4>
                <h5 className="font-bold text-[var(--text)] text-[length:var(--text-sm)] mb-1">Data Privacy</h5>
                <p className="text-[length:var(--text-xs)] text-[var(--text-2)] leading-relaxed">
                  Zero-Training Guarantee. We never train models on your data. GDPR data subject
                  rights (export, deletion) supported on request.
                </p>
              </div>
            </section>

            <section className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--surface-2)] text-[var(--text-2)]">
                <Server className="h-5 w-5" />
              </div>
              <div>
                <h4 className="font-semibold text-[var(--text-2)] mb-1 uppercase tracking-wider text-[length:var(--text-2xs)]">Encryption</h4>
                <h5 className="font-bold text-[var(--text)] text-[length:var(--text-sm)] mb-1">Encryption</h5>
                <p className="text-[length:var(--text-xs)] text-[var(--text-2)] leading-relaxed">
                  E2EE in transit and at rest using AES-256-GCM.
                  <br />
                  <span className="italic text-[var(--text-muted)] text-[length:var(--text-2xs)]">All data is encrypted in transit and at rest.</span>
                </p>
              </div>
            </section>
          </div>

          {/* Column 2 */}
          <div className="space-y-6">
            <section className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--surface-2)] text-[var(--text-2)]">
                <Users className="h-5 w-5" />
              </div>
              <div>
                <h4 className="font-semibold text-[var(--text-2)] mb-1 uppercase tracking-wider text-[length:var(--text-2xs)]">Access Control</h4>
                <h5 className="font-bold text-[var(--text)] text-[length:var(--text-sm)] mb-1">SSO & SAML — Roadmap</h5>
                <p className="text-[length:var(--text-xs)] text-[var(--text-2)] leading-relaxed">
                  Okta, Azure AD, and Google Workspace integration is planned, not yet available.
                </p>
              </div>
            </section>

            <section className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--surface-2)] text-[var(--text-2)]">
                <History className="h-5 w-5" />
              </div>
              <div>
                <h4 className="font-semibold text-[var(--text-2)] mb-1 uppercase tracking-wider text-[length:var(--text-2xs)]">Governance</h4>
                <h5 className="font-bold text-[var(--text)] text-[length:var(--text-sm)] mb-1">Audit Logs & Retention</h5>
                <p className="text-[length:var(--text-xs)] text-[var(--text-2)] leading-relaxed">
                  Comprehensive audit trails for all actions. Configurable data retention policies to meet legal requirements.
                </p>
              </div>
            </section>

            <section className="flex gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius)] bg-[var(--surface-2)] text-[var(--text-2)]">
                <Globe className="h-5 w-5" />
              </div>
              <div>
                <h4 className="font-semibold text-[var(--text-2)] mb-1 uppercase tracking-wider text-[length:var(--text-2xs)]">Network</h4>
                <h5 className="font-bold text-[var(--text)] text-[length:var(--text-sm)] mb-1">Zero-Trust Architecture</h5>
                <p className="text-[length:var(--text-xs)] text-[var(--text-2)] leading-relaxed">
                  All inter-component communication is authenticated and encrypted via internal PKI. No plaintext data on the wire.
                </p>
              </div>
            </section>
          </div>
        </div>

        <button
          onClick={onClose}
          className="mt-8 w-full rounded-[var(--radius-lg)] bg-[var(--accent)] py-3 text-[length:var(--text-sm)] font-semibold text-[var(--accent-text)] transition-all hover:opacity-90 active:scale-[0.98]"
        >
          Got it
        </button>
      </div>
    </div>,
    document.body
  );
}
