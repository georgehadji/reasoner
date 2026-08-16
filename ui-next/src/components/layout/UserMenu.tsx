'use client';

import { useState, useRef, useEffect } from 'react';
import { useAppStore } from '@/stores/app-store';
import { signOut } from '@/lib/auth';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useSubscription } from '@/hooks/useSubscription';
import { User, LayoutDashboard, CreditCard, LogOut, ChevronDown, Info } from 'lucide-react';
import { cn } from '@/lib/utils';

const MENU_LINKS = [
  { label: 'Dashboard', href: '/dashboard', Icon: LayoutDashboard },
  { label: 'Settings', href: '/settings', Icon: User },
  { label: 'Pricing', href: '/pricing', Icon: CreditCard },
  { label: 'About', href: '/about', Icon: Info },
];

export function UserMenu() {
  const user = useAppStore((s) => s.user);
  const logout = useAppStore((s) => s.logout);
  const router = useRouter();
  const pathname = usePathname() ?? '/';
  const { subscription } = useSubscription();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  /* Escape closes and hands focus back to the trigger — otherwise keyboard
     users land at the top of the document after dismissing the popup. */
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  if (!user) return null;

  const tierLabel = subscription?.tier ? subscription.tier.charAt(0).toUpperCase() + subscription.tier.slice(1) : 'Free';

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch {
      // ignore
    }
    logout();
    router.push('/login');
  };

  const itemClass =
    'flex min-h-[44px] w-full items-center gap-[var(--space-2)] border-l-2 px-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)]';

  return (
    <div className="relative" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 items-center gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-3)]"
        aria-expanded={open}
        aria-controls="user-menu-panel"
        /* The visible email and tier must stay in the accessible name
           (WCAG 2.5.3). A bare "User menu" label overrode them, so a
           screen-reader user could not tell which account was signed in. */
        aria-label={`Account menu for ${user.email}`}
      >
        <User className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
        <span className="hidden max-w-[120px] truncate sm:inline">{user.email}</span>
        <span className="inline-flex items-center rounded-[var(--radius-pill)] bg-[var(--accent-dim)] px-1.5 py-0.5 text-[length:var(--text-2xs)] leading-[var(--lh-tight)] font-medium text-[var(--accent)]">
          {tierLabel}
        </span>
        <ChevronDown
          className={cn(
            'h-3.5 w-3.5 text-[var(--text-muted)] transition-transform duration-[var(--dur-state)] ease-[var(--ease-standard)]',
            open && 'rotate-180',
          )}
          aria-hidden="true"
        />
      </button>

      {open && (
        <nav
          id="user-menu-panel"
          className="absolute right-0 top-full z-50 mt-1 w-52 overflow-hidden rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] py-1 shadow-[var(--shadow-lg)]"
          aria-label="Account"
        >
          {MENU_LINKS.map(({ label, href, Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                onClick={() => setOpen(false)}
                className={cn(
                  itemClass,
                  active
                    ? 'border-[var(--accent)] bg-[var(--accent-dim)] font-medium text-[var(--accent)]'
                    : 'border-transparent text-[var(--text)] hover:bg-[var(--surface-2)]',
                )}
              >
                <Icon
                  className={cn('h-4 w-4', active ? 'text-[var(--accent)]' : 'text-[var(--text-muted)]')}
                  aria-hidden="true"
                />
                {label}
              </Link>
            );
          })}

          <div className="my-1 h-px bg-[var(--border)]" />

          <button
            type="button"
            onClick={handleSignOut}
            className={cn(itemClass, 'border-transparent text-[var(--red)] hover:bg-[var(--red-bg)]')}
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Log out
          </button>
        </nav>
      )}
    </div>
  );
}
