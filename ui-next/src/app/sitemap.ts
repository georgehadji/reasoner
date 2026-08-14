import type { MetadataRoute } from 'next';
import { DOCS } from '@/lib/docs';
import { absoluteUrl } from '@/lib/site';

/**
 * XML sitemap, served at /sitemap.xml.
 *
 * Only public, indexable pages belong here. Authenticated surfaces are
 * excluded — listing a page that returns a login wall wastes crawl budget and
 * teaches crawlers that the sitemap is unreliable.
 */

interface Entry {
  path: string;
  changeFrequency: MetadataRoute.Sitemap[number]['changeFrequency'];
  priority: number;
}

const MARKETING_PAGES: Entry[] = [
  { path: '/', changeFrequency: 'weekly', priority: 1.0 },
  { path: '/pricing', changeFrequency: 'weekly', priority: 0.9 },
  { path: '/about', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/faq', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/help', changeFrequency: 'monthly', priority: 0.7 },
  { path: '/contact', changeFrequency: 'yearly', priority: 0.4 },
  { path: '/security', changeFrequency: 'monthly', priority: 0.5 },
  { path: '/privacy', changeFrequency: 'yearly', priority: 0.3 },
  { path: '/terms', changeFrequency: 'yearly', priority: 0.3 },
  { path: '/cookies', changeFrequency: 'yearly', priority: 0.3 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return [
    ...MARKETING_PAGES.map(({ path, changeFrequency, priority }) => ({
      url: absoluteUrl(path),
      lastModified,
      changeFrequency,
      priority,
    })),
    {
      url: absoluteUrl('/docs'),
      lastModified,
      changeFrequency: 'weekly' as const,
      priority: 0.9,
    },
    ...DOCS.map((doc) => ({
      url: absoluteUrl(`/docs/${doc.slug}`),
      lastModified,
      changeFrequency: 'monthly' as const,
      priority: 0.8,
    })),
  ];
}
