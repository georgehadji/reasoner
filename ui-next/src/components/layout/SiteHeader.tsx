'use client';

import { useEffect, useState } from 'react';
import { useAppStore } from '@/stores/app-store';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { UserMenu } from './UserMenu';
import { Logo } from '@/components/brand/Logo';
import { SecurityBadge } from './SecurityBadge';
import { cn } from '@/lib/utils';

export function SiteHeader() {
  const user = useAppStore((s) => s.user);
  const router = useRouter();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className={cn(
        'fixed top-0 left-0 right-0 z-50',
        'border-b border-transparent backdrop-blur-xl saturate-[1.3]',
        'transition-[background-color,border-color,box-shadow] duration-300',
        scrolled
          ? 'bg-[rgba(10,15,22,0.70)] border-[rgba(128,128,128,0.11)] shadow-[var(--shadow-lg)]'
          : 'bg-transparent'
      )}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        {/* Logo */}
        <Link
          href="/"
          className="transition-opacity duration-200 hover:opacity-80"
        >
          <Logo showWordmark size={26} />
        </Link>

        {/* Nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {[
            { label: 'About', href: '/about' },
            { label: 'Pricing', href: '/pricing' },
            { label: 'Docs', href: '/docs' },
          ].map(({ label, href }) => (
            <Link
              key={href}
              href={href}
              className="flex h-10 items-center rounded-lg px-4 text-sm font-medium text-[var(--text-muted)] transition-colors duration-200 hover:text-[var(--text)]"
            >
              {label}
            </Link>
          ))}
        </nav>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <SecurityBadge className="hidden sm:flex" />
          {user ? (
            <>
              <button
                onClick={() => router.push('/chat')}
                className="hidden h-10 items-center rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[var(--accent-text)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-[0.97] sm:inline-flex"
              >
                Open App
              </button>
              <UserMenu />
            </>
          ) : (
            <>
              <button
                onClick={() => router.push('/login')}
                className="flex h-10 items-center rounded-lg px-4 text-sm font-medium text-[var(--text-muted)] transition-colors duration-200 hover:text-[var(--text)]"
              >
                Sign in
              </button>
              <button
                onClick={() => router.push('/chat')}
                className="flex h-10 items-center rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[var(--accent-text)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-[0.97]"
              >
                Get started
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
