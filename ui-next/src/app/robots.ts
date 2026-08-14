import type { MetadataRoute } from 'next';
import { AI_CRAWLERS, NOINDEX_PATHS, absoluteUrl } from '@/lib/site';

/**
 * robots.txt.
 *
 * AI answer engines are given an explicit allow rule rather than being left to
 * the wildcard. Several of them treat an absent named rule as ambiguous, and
 * the goal here is the opposite of exclusion: the documentation exists to be
 * quoted back to people asking questions about Reasoner.
 *
 * Authenticated and transactional routes are disallowed for every agent — they
 * return login walls or user-specific data and have no business being indexed.
 */
export default function robots(): MetadataRoute.Robots {
  const disallow = [...NOINDEX_PATHS];

  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow,
      },
      ...AI_CRAWLERS.map((userAgent) => ({
        userAgent,
        allow: ['/', '/docs/'],
        disallow,
      })),
    ],
    sitemap: absoluteUrl('/sitemap.xml'),
    host: absoluteUrl('/').replace(/\/$/, ''),
  };
}
