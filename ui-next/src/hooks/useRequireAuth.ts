'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { selectAuthStatus, useAppStore, type AuthStatus } from '@/stores/app-store';

/**
 * Route guard for pages that need a signed-in user. Redirects only once the
 * session has settled as `anonymous`, and only from an effect, never during
 * render. The page decides it needs a user; the transport never navigates.
 *
 *   const status = useRequireAuth();
 *   if (status !== 'authenticated') return null;
 */
export function useRequireAuth(): AuthStatus {
  const status = useAppStore(selectAuthStatus);
  const router = useRouter();
  const pathname = usePathname() ?? '/';

  useEffect(() => {
    if (status === 'anonymous') {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [status, pathname, router]);

  return status;
}
