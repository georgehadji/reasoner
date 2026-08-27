'use client';

import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '@/stores/app-store';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Lock, Menu, X } from 'lucide-react';
import { UserMenu } from './UserMenu';
import { Logo } from '@/components/brand/Logo';
import { SecurityModal } from './SecurityModal';
import { Button } from '@/components/ui/Button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { cn } from '@/lib/utils';

const NAV_LINKS = [
  { label: 'Capabilities', href: '/capabilities' },
  { label: 'How it works', href: '/how-it-works' },
  { label: 'About', href: '/about' },
  { label: 'Pricing', href: '/pricing' },
  { label: 'Docs', href: '/docs' },
];

/** `/docs/streaming` must light up the `/docs` tag, so match the prefix too. */
function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SiteHeader() {
  const user = useAppStore((s) => s.user);
  const router = useRouter();
  const pathname = usePathname() ?? '/';
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const drawerRef = useRef<HTMLDialogElement>(null);
  /* One modal for both triggers, owned here rather than by two SecurityBadges.
     The drawer trigger has to close the drawer before opening it: showModal()
     makes everything outside the <dialog> inert, so a security modal rendered
     while the drawer is open is visible but unfocusable, and clicks at its
     centre hit-test through to the drawer's nav underneath. */
  const [securityOpen, setSecurityOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  /* A modal <dialog> already traps Tag, closes on Escape and returns focus to
     whatever opened it. Every line of a hand-rolled focus manager here would
     be re-implementing the platform. */
  useEffect(() => {
    const el = drawerRef.current;
    if (!el) return;
    if (menuOpen && !el.open) el.showModal();
    if (!menuOpen && el.open) el.close();
  }, [menuOpen]);

  /* Rotating a tablet past the md breakpoint with the drawer open would leave
     the page inert behind a menu that is no longer reachable. */
  useEffect(() => {
    if (!menuOpen) return;
    const mq = window.matchMedia('(min-width: 768px)');
    const sync = () => { if (mq.matches) setMenuOpen(false); };
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, [menuOpen]);

  const navLinkClass = (active: boolean) =>
    cn(
      'group relative flex h-10 items-center rounded-[var(--radius)] px-[var(--space-4)]',
      'text-[length:var(--text-sm)] leading-[var(--lh-ui)] font-medium',
      'transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)]',
      active
        ? 'text-[var(--accent)]'
        : 'text-[var(--text-muted)] hover:text-[var(--text)]',
    );

  return (
    <header
      className={cn(
        'fixed top-0 left-0 right-0 z-50',
        'border-b border-transparent backdrop-blur-xl saturate-[1.3]',
        'transition-[background-color,border-color,box-shadow] duration-[var(--dur-state)] ease-[var(--ease-standard)]',
        scrolled
          ? 'glass border-[var(--border)] shadow-[var(--shadow-lg)]'
          : 'bg-transparent',
      )}
    >
      <div className="mx-auto flex h-[var(--space-16)] max-w-[var(--width-wide)] items-center justify-between gap-[var(--space-3)] px-[var(--gutter)]">
        {/* Logo */}
        <Link
          href="/"
          aria-current={pathname === '/' ? 'page' : undefined}
          className="rounded-[var(--radius)] transition-opacity duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:opacity-80"
        >
          <Logo showWordmark size={26} />
        </Link>

        {/* Desktop nav */}
        <nav aria-label="Main" className="hidden items-center gap-[var(--space-1)] md:flex">
          {NAV_LINKS.map(({ label, href }) => {
            const active = isActivePath(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                className={navLinkClass(active)}
              >
                {label}
                {/* Persistent indicator: present for the active route, wiped in
                    on hover. Same rule, two speeds — hover is a preview, an
                    active change is a state change. */}
                <span
                  aria-hidden="true"
                  className={cn(
                    'pointer-events-none absolute inset-x-[var(--space-4)] bottom-[var(--space-1)]',
                    'h-[2px] origin-left rounded-[var(--radius-pill)] bg-[var(--accent)]',
                    'transition-transform duration-[var(--dur-state)] ease-[var(--ease-entrance)]',
                    'group-hover:scale-x-100 group-hover:duration-[var(--dur-micro)]',
                    active ? 'scale-x-100' : 'scale-x-0',
                  )}
                />
              </Link>
            );
          })}
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-[var(--space-2)] sm:gap-[var(--space-3)]">
          <ThemeToggle />
          <Button
            variant="outline"
            size="sm"
            leftIcon={<Lock className="h-3.5 w-3.5" />}
            onClick={() => setSecurityOpen(true)}
            className="hidden sm:flex"
          >
            Secure
          </Button>
          {user ? (
            <>
              <button
                onClick={() => router.push('/chat')}
                className="hidden h-10 items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] font-semibold text-[var(--accent-text)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--accent-hover)] active:scale-[0.97] sm:inline-flex"
              >
                Open App
              </button>
              <UserMenu />
            </>
          ) : (
            <>
              <button
                onClick={() => router.push('/login')}
                className="hidden h-10 items-center rounded-[var(--radius)] px-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] font-medium text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:text-[var(--text)] sm:flex"
              >
                Sign in
              </button>
              <button
                onClick={() => router.push('/chat')}
                className="flex h-10 items-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] font-semibold text-[var(--accent-text)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--accent-hover)] active:scale-[0.97]"
              >
                Get started
              </button>
            </>
          )}

          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={menuOpen}
            aria-controls="site-nav-drawer"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-2)] hover:text-[var(--text)] md:hidden"
          >
            <Menu className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Mobile drawer. Full-height rows, not a shrunken desktop menu. */}
      <dialog
        ref={drawerRef}
        id="site-nav-drawer"
        aria-label="Site navigation"
        onClose={() => setMenuOpen(false)}
        onClick={(e) => { if (e.target === e.currentTarget) setMenuOpen(false); }}
        /* The scrim lives on the dialog itself rather than on `::backdrop`:
           the element fills the viewport anyway, and this keeps the styling
           independent of pseudo-element variant support. */
        className="m-0 h-full max-h-none w-full max-w-none border-0 bg-[var(--scrim)] p-0 text-[var(--text)] backdrop-blur-sm"
      >
        <div className="animate-phase-reveal ml-auto flex h-full w-[min(20rem,86vw)] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
          <div className="flex h-[var(--space-16)] shrink-0 items-center justify-between gap-[var(--space-3)] border-b border-[var(--border)] px-[var(--space-4)]">
            <Logo showWordmark size={24} />
            <button
              type="button"
              onClick={() => setMenuOpen(false)}
              aria-label="Close navigation menu"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          {/* The dialog already carries the accessible name for this region —
              a second "Main" landmark would just duplicate it. */}
          <nav className="flex flex-1 flex-col gap-[var(--space-1)] overflow-y-auto p-[var(--space-3)] scrollbar-thin">
            {NAV_LINKS.map(({ label, href }) => {
              const active = isActivePath(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setMenuOpen(false)}
                  className={cn(
                    'flex min-h-[44px] items-center rounded-[var(--radius)] border-l-2 px-[var(--space-4)]',
                    'text-[length:var(--text-base)] leading-[var(--lh-ui)] font-medium',
                    'transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)]',
                    active
                      ? 'border-[var(--accent)] bg-[var(--accent-dim)] text-[var(--accent)]'
                      : 'border-transparent text-[var(--text-2)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]',
                  )}
                >
                  {label}
                </Link>
              );
            })}
          </nav>

          <div className="flex shrink-0 flex-col gap-[var(--space-2)] border-t border-[var(--border)] p-[var(--space-3)]">
            {/* Below sm the header badge is hidden and the drawer was the only
                place left to reach it — so it was reachable nowhere. sm:hidden
                because from sm up the header shows it and the drawer is still
                open until md. */}
            <div className="flex items-center justify-between gap-[var(--space-2)]">
              <span className="text-[length:var(--text-sm)] text-[var(--text-muted)]">Theme</span>
              <ThemeToggle />
            </div>
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Lock className="h-3.5 w-3.5" />}
              onClick={() => { setMenuOpen(false); setSecurityOpen(true); }}
              className="w-full justify-center sm:hidden"
            >
              Secure
            </Button>
            {user ? (
              <button
                onClick={() => { setMenuOpen(false); router.push('/chat'); }}
                className="flex min-h-[44px] items-center justify-center rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] font-semibold text-[var(--accent-text)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--accent-hover)] active:scale-[0.97]"
              >
                Open App
              </button>
            ) : (
              <button
                onClick={() => { setMenuOpen(false); router.push('/login'); }}
                className="flex min-h-[44px] items-center justify-center rounded-[var(--radius)] border border-[var(--border)] px-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] font-medium text-[var(--text-2)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:border-[var(--border-strong)] hover:text-[var(--text)]"
              >
                Sign in
              </button>
            )}
          </div>
        </div>
      </dialog>

      {/* Sibling of the drawer, never a child of it. It portals to <body>, so
          the header's own backdrop-blur does not become its containing block. */}
      <SecurityModal isOpen={securityOpen} onClose={() => setSecurityOpen(false)} />
    </header>
  );
}
