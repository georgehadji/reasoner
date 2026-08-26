/**
 * Canonical site identity — the single source of truth for every absolute URL
 * the app emits (metadata, sitemap, robots, JSON-LD, OpenGraph).
 *
 * Search engines and AI crawlers treat differing hostnames as different sites,
 * so all of these must derive from one value rather than being hardcoded per
 * page.
 */

import { CAPABILITIES } from './capabilities.generated';

function normalizeOrigin(raw: string | undefined, fallback: string): string {
  const value = (raw || '').trim() || fallback;
  const withProtocol = /^https?:\/\//.test(value) ? value : `https://${value}`;
  return withProtocol.replace(/\/+$/, '');
}

export const SITE_URL = normalizeOrigin(
  process.env.NEXT_PUBLIC_SITE_URL,
  'https://reasoner.app',
);

export const SITE = {
  name: 'Reasoner',
  /**
   * The company that builds and operates Reasoner — the single source of truth
   * for it. Feeds the JSON-LD Organization node and every "operated by" line in
   * the UI (SiteFooter, /about), so the company can be renamed here alone.
   * `name` above is the product and is deliberately separate: the two are not
   * the same thing and must be able to differ.
   */
  legalName: 'Polytonic',
  /** Renders as the browser title on every route, so it has to say what the
   *  product does rather than how it feels. */
  tagline: 'Reasoning with the argument attached',
  /** Used as the default meta description and the JSON-LD description. */
  description:
    'Reasoner is a multi-method AI reasoning engine. It decomposes a problem, runs cross-lab models in parallel, critiques and stress-tests the candidates, then synthesises an answer with explicit VERIFIED / HYPOTHESIS / UNKNOWN labels.',
  /** Short form for OpenGraph cards, where space is tight. Derived from
   *  capabilities.generated.ts so it can't drift from the live registry. */
  shortDescription: `${CAPABILITIES.methods} reasoning methods · ${CAPABILITIES.routableModels}+ models · epistemically labelled answers`,
  url: SITE_URL,
  locale: 'en_US',
  twitter: '@reasonerapp',
} as const;

/** Absolute URL for a site-relative path. */
export function absoluteUrl(path = '/'): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

/**
 * Routes that must never be indexed: authenticated surfaces, transactional
 * flows, and API endpoints. Kept here so robots.ts and sitemap.ts cannot drift.
 */
export const NOINDEX_PATHS: readonly string[] = [
  '/api/',
  '/chat',
  '/dashboard',
  '/settings',
  '/login',
  '/signup',
  '/forgot-password',
  '/reset-password',
];

/** Crawlers that read pages to answer questions, not just to rank them. */
export const AI_CRAWLERS: readonly string[] = [
  'GPTBot',
  'OAI-SearchBot',
  'ChatGPT-User',
  'ClaudeBot',
  'Claude-User',
  'Claude-SearchBot',
  'anthropic-ai',
  'PerplexityBot',
  'Perplexity-User',
  'Google-Extended',
  'Applebot-Extended',
  'CCBot',
  'cohere-ai',
  'Meta-ExternalAgent',
  'Bytespider',
  'DuckAssistBot',
  'MistralAI-User',
  'YouBot',
];
