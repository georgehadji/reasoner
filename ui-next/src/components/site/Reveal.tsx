'use client';

import { useEffect } from 'react';

/**
 * Arms every `[data-reveal]` element on the page for a one-time entrance.
 *
 * Elements are visible in the server render; only this script hides them,
 * and only once IntersectionObserver exists and motion is allowed, so a
 * reader without script, a printer, or a reduced-motion user sees the page
 * whole from the start.
 */
export function Reveal() {
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const targets = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'));
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        }
      },
      { rootMargin: '0px 0px -10% 0px' },
    );

    for (const el of targets) {
      // Already on screen at load: leave it alone rather than flash it.
      if (el.getBoundingClientRect().top < window.innerHeight) continue;
      el.classList.add('site-reveal-armed');
      io.observe(el);
    }
    return () => io.disconnect();
  }, []);

  return null;
}
