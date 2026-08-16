'use client';

import { useTheme } from 'next-themes';
import { Sun, Moon } from 'lucide-react';
import { useIsDark } from '@/hooks/useIsDark';

export function ThemeToggle() {
  const { setTheme } = useTheme();
  // Mount-gated: `resolvedTheme` is undefined server-side, so deriving the
  // label from it directly rendered "Switch to dark theme" into the HTML and
  // then disagreed with the hydrated tree. React leaves attribute mismatches
  // alone, so a dark-mode user was left with a button labelled as if they
  // were in light mode. The icons are pure CSS `dark:` variants and were
  // never affected.
  const { isDark, mounted } = useIsDark();

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      // `relative` positions the absolutely-placed Moon icon below; without
      // it the icon resolves against the nearest positioned ancestor.
      className="relative flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] transition-colors hover:bg-[var(--surface-hover)]"
      // Neutral until the theme is known — true in either direction, rather
      // than a coin flip that is wrong half the time.
      aria-label={!mounted ? 'Toggle theme' : isDark ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </button>
  );
}
