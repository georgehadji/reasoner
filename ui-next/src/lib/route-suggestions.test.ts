import { describe, expect, it } from 'vitest';

import sitemap from '@/app/sitemap';
import { DOCS } from '@/lib/docs';
import { SITE_URL } from '@/lib/site';
import {
  DOC_SLUGS,
  FEATURED_ROUTES,
  MAX_DISPLAY_PATH,
  NAVIGABLE_ROUTES,
  sanitizeDisplayPath,
  suggestRoutes,
} from '@/lib/route-suggestions';

/**
 * The route table in `route-suggestions.ts` is a deliberate copy: importing the
 * real sources would drag every doc body into the client bundle. These first
 * two tests are what make the copy safe — they fail the moment a page is added
 * or renamed anywhere else in the app.
 */
describe('route table parity', () => {
  it('knows every path the sitemap advertises', () => {
    const sitemapPaths = sitemap()
      .map((entry) => entry.url.replace(SITE_URL, ''))
      .map((path) => path || '/');
    const known = new Set(NAVIGABLE_ROUTES.map((route) => route.href));

    const missing = sitemapPaths.filter((path) => !known.has(path));
    expect(missing).toEqual([]);
  });

  it('mirrors the live doc slugs exactly', () => {
    expect([...DOC_SLUGS].sort()).toEqual(DOCS.map((doc) => doc.slug).sort());
  });

  it('resolves every featured destination and stays under the six-link ceiling', () => {
    expect(FEATURED_ROUTES.length).toBeLessThanOrEqual(6);
    for (const route of FEATURED_ROUTES) {
      expect(NAVIGABLE_ROUTES).toContain(route);
    }
  });
});

describe('sanitizeDisplayPath', () => {
  it('falls back to the root rather than rendering an empty echo', () => {
    expect(sanitizeDisplayPath('')).toBe('/');
    expect(sanitizeDisplayPath(null)).toBe('/');
    expect(sanitizeDisplayPath(undefined)).toBe('/');
  });

  it('leaves an ordinary path alone', () => {
    expect(sanitizeDisplayPath('/docs/api-reference')).toBe('/docs/api-reference');
  });

  it('strips control characters that would break the line', () => {
    expect(sanitizeDisplayPath('/do\u001Bcs[31m')).toBe('/docs[31m');
  });

  it('strips bidi overrides that would rewrite the surrounding sentence', () => {
    expect(sanitizeDisplayPath('/a\u202Eb\u200Bc')).toBe('/abc');
  });

  it('truncates a hostile long path instead of blowing out the layout', () => {
    const result = sanitizeDisplayPath(`/${'x'.repeat(4000)}`);
    expect(result.length).toBe(MAX_DISPLAY_PATH);
    expect(result.endsWith('…')).toBe(true);
  });

  it('always renders as a path', () => {
    expect(sanitizeDisplayPath('pricing')).toBe('/pricing');
  });
});

describe('suggestRoutes', () => {
  const top = (path: string) => suggestRoutes(path)[0]?.href;

  it('recovers from a single-character typo', () => {
    expect(top('/princing')).toBe('/pricing');
    expect(top('/setings')).toBe('/settings');
  });

  it('recovers from a transposition', () => {
    expect(top('/docs/qucikstart')).toBe('/docs/quickstart');
  });

  it('follows an editorial alias to the page that replaced it', () => {
    expect(top('/blog')).toBe('/changelog');
    expect(top('/support')).toBe('/help');
    expect(top('/sign-in')).toBe('/login');
    expect(top('/register')).toBe('/signup');
    expect(top('/documentation')).toBe('/docs');
  });

  it('falls back to the section when only the leaf is wrong', () => {
    expect(top('/docs/this-page-never-existed')).toBe('/docs');
  });

  it('ignores a trailing slash, casing, query, and hash', () => {
    expect(top('/Princing/?utm_source=x#top')).toBe('/pricing');
  });

  it('ignores a pasted file extension', () => {
    expect(top('/pricing.html')).toBe('/pricing');
  });

  it('stays silent rather than guessing wildly', () => {
    expect(suggestRoutes('/qwertyuiopasdfgh')).toEqual([]);
  });

  it('returns nothing for the root, which is never a 404', () => {
    expect(suggestRoutes('/')).toEqual([]);
    expect(suggestRoutes('')).toEqual([]);
  });

  it('never suggests the page the visitor is already on', () => {
    for (const suggestion of suggestRoutes('/pricing')) {
      expect(suggestion.href).not.toBe('/pricing');
    }
  });

  it('ranks by confidence and honours the limit', () => {
    const results = suggestRoutes('/doc', 2);
    expect(results.length).toBeLessThanOrEqual(2);
    for (let i = 1; i < results.length; i++) {
      expect(results[i - 1].score).toBeGreaterThanOrEqual(results[i].score);
    }
  });

  it('survives a hostile path without throwing', () => {
    expect(() => suggestRoutes(`/${'a'.repeat(5000)}`)).not.toThrow();
    expect(() => suggestRoutes('/../../etc/passwd')).not.toThrow();
  });
});
