import type { Metadata } from 'next';

import { NotFoundView } from '@/components/not-found/NotFoundView';

/**
 * The App Router's reserved handler for unmatched routes and for any
 * `notFound()` call. Next.js serves it with a real 404 status, which is what
 * keeps a mistyped URL out of the index in the first place; `noindex` here is
 * the belt to that braces, for crawlers that reached this markup some other
 * way. `follow` stays on so the recovery links still pass crawlers back into
 * the live site rather than stranding them.
 *
 * This file is a server component so the metadata above is static. Everything
 * visible lives in `NotFoundView`, which has to be a client component: the
 * requested path is the page's most useful content, and `usePathname()` is the
 * only way to read it here.
 */
export const metadata: Metadata = {
  title: 'Page not found',
  description:
    'That address does not resolve. Find the page you were looking for, or put the question to Reasoner instead.',
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return <NotFoundView />;
}
