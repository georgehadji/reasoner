'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';

/**
 * Resolved dark-mode flag that is safe to branch on during render.
 *
 * Two traps this closes, both of which shipped:
 *
 * 1. `theme` is the literal string `"system"` until the user picks one, so
 *    `theme === 'dark'` is false for every system-dark visitor. `CodeBlock`
 *    read `theme` and served the light syntax palette on a dark page.
 *
 * 2. `resolvedTheme` is correct but `undefined` on the server and on the
 *    first client render — next-themes cannot know the theme until it has
 *    run in the browser. Branching on it directly makes the server HTML and
 *    the hydrated tree disagree, and React does not patch up attribute
 *    mismatches: the server's value sticks. `ThemeToggle` shipped an
 *    `aria-label` that said "Switch to dark theme" while in dark mode.
 *
 * `mounted` is false for exactly that first render. Render something
 * theme-neutral while it is false, then the real thing once it flips.
 */
export function useIsDark(): { isDark: boolean; mounted: boolean } {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return { isDark: mounted && resolvedTheme === 'dark', mounted };
}
