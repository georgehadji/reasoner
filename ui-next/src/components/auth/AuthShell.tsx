import type { ReactNode } from 'react';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { SiteHeader } from '@/components/layout/SiteHeader';

/**
 * The sign-in, sign-up and password screens in the site world "The product
 * performs": they are the step between the marketing pages and the app, so
 * they share the site's charcoal and sage. `.site` remaps the app roles
 * (--bg, --accent, --surface, --text, --border) to the site palette, so the
 * forms inside keep their own field and Button styles unchanged.
 *
 * The claim sits left, the form right on the surface tone; on a phone the
 * claim comes first with less air above it, so the form is close behind.
 */
export function AuthShell({
  lines,
  lead,
  children,
}: {
  lines: [string, string];
  lead: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="grid flex-1 lg:grid-cols-2">
        <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-24)] lg:pb-[var(--space-16)] lg:pt-[var(--space-32)]">
          <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
            <span className="site-line">
              <span>{lines[0]}</span>
            </span>
            <span className="site-line">
              <span>{lines[1]}</span>
            </span>
          </h1>
          <p className="site-after-headline mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
            {lead}
          </p>
        </div>
        <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
          {/* The form is the screen's one fragment, framed like a hero fragment. */}
          <div
            data-ui
            data-reveal
            className="flex w-full flex-col gap-[var(--space-5)] rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] p-[var(--space-4)] sm:p-[var(--space-8)] lg:max-w-[var(--site-fragment)]"
          >
            {children}
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
