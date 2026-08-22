/**
 * Route recovery for the 404 page.
 *
 * A 404 is a navigation failure, and the single most useful thing a 404 page
 * can do is guess where the visitor meant to go. Everything else on that page
 * is decoration; this module is the part that actually recovers the session.
 *
 * The route table is a hand-written literal rather than an import of
 * `sitemap.ts` or `docs.ts` on purpose: this runs in the browser, and
 * `docs.ts` carries every doc body as a string. Importing it to learn twelve
 * slugs would ship tens of kilobytes of markdown to a page whose whole job is
 * to get the visitor off it. `route-suggestions.test.ts` asserts this table
 * against both real sources, so the copy cannot drift silently.
 */

export interface NavigableRoute {
  href: string;
  label: string;
  /** One line of orientation, shown under the label in the recovery grid. */
  blurb: string;
  /**
   * Tie-break weight, mirroring sitemap priority. When two routes score the
   * same, the more important destination is the better guess.
   */
  weight: number;
  /**
   * Words a visitor might type instead of the real slug: renames, competitor
   * vocabulary, and the spellings other products use for the same page. An
   * alias hit outranks any amount of string similarity.
   */
  aliases?: readonly string[];
}

/** Public marketing surface. Paths mirror `app/sitemap.ts`. */
const MARKETING_ROUTES: readonly NavigableRoute[] = [
  {
    href: '/',
    label: 'Home',
    blurb: 'What Reasoner is and what it is for.',
    weight: 1.0,
    aliases: ['home', 'index', 'main', 'start'],
  },
  {
    href: '/pricing',
    label: 'Pricing',
    blurb: 'Credit bundles and what a run actually costs.',
    weight: 0.9,
    aliases: ['plans', 'plan', 'billing', 'cost', 'costs', 'price', 'subscribe'],
  },
  {
    href: '/how-it-works',
    label: 'How it works',
    blurb: 'The pipeline, phase by phase, end to end.',
    weight: 0.8,
    aliases: ['how', 'pipeline', 'phases', 'architecture', 'features', 'product'],
  },
  {
    href: '/docs',
    label: 'Documentation',
    blurb: 'Guides, the API reference, and integration notes.',
    weight: 0.9,
    aliases: ['doc', 'documentation', 'guide', 'guides', 'manual', 'reference', 'api'],
  },
  {
    href: '/about',
    label: 'About',
    blurb: 'The thesis behind the architecture.',
    weight: 0.7,
    aliases: ['company', 'team', 'mission', 'story'],
  },
  {
    href: '/faq',
    label: 'FAQ',
    blurb: 'The questions that come up before signing up.',
    weight: 0.7,
    aliases: ['questions', 'answers'],
  },
  {
    href: '/help',
    label: 'Help centre',
    blurb: 'Troubleshooting and account questions.',
    weight: 0.7,
    aliases: ['support', 'assistance'],
  },
  {
    href: '/contact',
    label: 'Contact',
    blurb: 'Reach a human.',
    weight: 0.4,
    aliases: ['email', 'sales', 'reach-us', 'get-in-touch'],
  },
  {
    href: '/security',
    label: 'Security',
    blurb: 'How data is handled, retained, and isolated.',
    weight: 0.5,
    aliases: ['trust', 'compliance', 'soc2'],
  },
  {
    href: '/subprocessors',
    label: 'Sub-processors',
    blurb: 'Every third party in the data path.',
    weight: 0.4,
    aliases: ['vendors', 'processors', 'third-parties'],
  },
  {
    href: '/changelog',
    label: 'Changelog',
    blurb: 'What shipped, and when.',
    weight: 0.5,
    aliases: ['blog', 'news', 'updates', 'releases', 'release-notes', 'whats-new'],
  },
  {
    href: '/status',
    label: 'Status',
    blurb: 'Live provider and pipeline health.',
    weight: 0.4,
    aliases: ['uptime', 'incidents', 'health'],
  },
  {
    href: '/privacy',
    label: 'Privacy',
    blurb: 'The privacy policy.',
    weight: 0.3,
    aliases: ['privacy-policy', 'gdpr', 'data-policy'],
  },
  {
    href: '/terms',
    label: 'Terms',
    blurb: 'Terms of service.',
    weight: 0.3,
    aliases: ['tos', 'terms-of-service', 'legal', 'eula'],
  },
  {
    href: '/cookies',
    label: 'Cookies',
    blurb: 'The cookie policy.',
    weight: 0.3,
    aliases: ['cookie-policy', 'tracking'],
  },
];

/**
 * Authenticated and transactional surfaces. They are deliberately absent from
 * the sitemap, but they are exactly what a mistyped URL is usually aiming at,
 * so the matcher has to know them.
 */
const APP_ROUTES: readonly NavigableRoute[] = [
  {
    href: '/chat',
    label: 'Open Reasoner',
    blurb: 'Put the question to the pipeline instead.',
    weight: 0.95,
    aliases: ['app', 'ask', 'run', 'query', 'conversation', 'playground'],
  },
  {
    href: '/dashboard',
    label: 'Dashboard',
    blurb: 'Runs, spend, and usage.',
    weight: 0.6,
    aliases: ['account', 'usage', 'overview'],
  },
  {
    href: '/settings',
    label: 'Settings',
    blurb: 'Keys, presets, and preferences.',
    weight: 0.6,
    aliases: ['preferences', 'profile', 'config', 'configuration', 'options'],
  },
  {
    href: '/login',
    label: 'Sign in',
    blurb: 'Return to an existing account.',
    weight: 0.6,
    aliases: ['signin', 'sign-in', 'log-in', 'auth', 'authenticate'],
  },
  {
    href: '/signup',
    label: 'Create account',
    blurb: 'Start a new account.',
    weight: 0.6,
    aliases: ['sign-up', 'register', 'registration', 'join', 'get-started', 'trial'],
  },
];

/** Doc slugs, mirroring the `slug` field of every entry in `lib/docs.ts`. */
export const DOC_SLUGS: readonly string[] = [
  'quickstart',
  'reasoning-methods',
  'presets-and-models',
  'image-generation',
  'article-generation',
  'code-generation',
  'credits',
  'api-keys',
  'api-reference',
  'agent-integration',
  'security-and-privacy',
  'troubleshooting',
];

const DOC_ROUTES: readonly NavigableRoute[] = DOC_SLUGS.map((slug) => ({
  href: `/docs/${slug}`,
  label: slug.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase()),
  blurb: 'Documentation',
  weight: 0.8,
}));

export const NAVIGABLE_ROUTES: readonly NavigableRoute[] = [
  ...MARKETING_ROUTES,
  ...APP_ROUTES,
  ...DOC_ROUTES,
];

/**
 * The recovery grid on the 404 page. Guidance on error pages is consistent
 * that dumping the sitemap onto a 404 raises cognitive load on someone who is
 * already lost; a short, ranked list of the destinations people actually want
 * outperforms completeness. Six is the ceiling.
 */
const FEATURED_HREFS: readonly string[] = [
  '/chat',
  '/docs',
  '/how-it-works',
  '/pricing',
  '/status',
  '/help',
];

export const FEATURED_ROUTES: readonly NavigableRoute[] = FEATURED_HREFS.map(
  (href) => {
    const route = NAVIGABLE_ROUTES.find((r) => r.href === href);
    if (!route) throw new Error(`FEATURED_HREFS references unknown route: ${href}`);
    return route;
  },
);

/* ────────────────────────────────────────────────────────────────────────────
   Display sanitisation

   The path is attacker-controlled: anyone can send a victim a link and choose
   what this page echoes back. React escapes the text, so markup injection is
   not the risk. The risks are a 4 kB "path" destroying the layout, and bidi
   override characters rewriting the sentence around the echo. Both are handled
   here rather than in the component, so there is one place to audit.
   ────────────────────────────────────────────────────────────────────────── */

/** C0 and C1 control characters. */
const CONTROL_CHARS = /[\u0000-\u001F\u007F-\u009F]/g;
/** Bidi embedding, override, and isolate controls, plus the invisible marks. */
const BIDI_CHARS = /[\u200B-\u200F\u202A-\u202E\u2060-\u2064\u2066-\u2069\uFEFF]/g;

export const MAX_DISPLAY_PATH = 96;

/** Render-safe form of a requested path. Never returns an empty string. */
export function sanitizeDisplayPath(raw: string | null | undefined): string {
  const cleaned = (raw ?? '')
    .replace(CONTROL_CHARS, '')
    .replace(BIDI_CHARS, '')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) return '/';

  const withSlash = cleaned.startsWith('/') ? cleaned : `/${cleaned}`;

  return withSlash.length > MAX_DISPLAY_PATH
    ? `${withSlash.slice(0, MAX_DISPLAY_PATH - 1)}…`
    : withSlash;
}

/* ────────────────────────────────────────────────────────────────────────────
   Matching
   ────────────────────────────────────────────────────────────────────────── */

/** Lowercased path with query, hash, duplicate and trailing slashes removed. */
function normalizePath(raw: string): string {
  const withoutSuffix = raw.split(/[?#]/)[0] ?? '';
  const collapsed = withoutSuffix
    .toLowerCase()
    .replace(CONTROL_CHARS, '')
    .replace(BIDI_CHARS, '')
    .replace(/\/{2,}/g, '/')
    .replace(/\/+$/, '');
  return collapsed || '/';
}

/** Word-ish pieces of a path: `/docs/api-reference` gives docs, api, reference. */
function tokenize(path: string): string[] {
  return path
    .split(/[/\-_.]+/)
    .filter(Boolean)
    // Drop file extensions people paste from other sites: `/pricing.html`.
    .filter((t) => !['html', 'htm', 'php', 'aspx', 'jsp'].includes(t));
}

/** Classic Levenshtein edit distance, two-row variant. */
function editDistance(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;

  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);

  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      row[j] = Math.min(
        (row[j - 1] ?? 0) + 1,
        (prev[j] ?? 0) + 1,
        (prev[j - 1] ?? 0) + cost,
      );
    }
    prev = row;
  }

  return prev[b.length] ?? Math.max(a.length, b.length);
}

/** Edit distance rescaled to 0-1, where 1 is identical. */
function similarity(a: string, b: string): number {
  const longest = Math.max(a.length, b.length);
  if (longest === 0) return 1;
  return 1 - editDistance(a, b) / longest;
}

/**
 * How well `route` explains `input`, in 0-1.
 *
 * Three signals, strongest wins:
 *   - an alias hit, which is an explicit editorial mapping and beats everything
 *   - similarity of the last segment, which catches typos (`/princing`)
 *   - token overlap, which catches reordering and extra segments
 *
 * A route whose href prefixes the input gets a bonus: `/docs/does-not-exist`
 * should land on `/docs` even though the strings barely resemble each other.
 */
function scoreRoute(route: NavigableRoute, input: string): number {
  const normalizedInput = normalizePath(input);
  const normalizedHref = normalizePath(route.href);

  if (normalizedInput === normalizedHref) return 1;

  const inputTokens = tokenize(normalizedInput);
  const routeTokens = tokenize(normalizedHref);
  if (inputTokens.length === 0) return 0;

  let score = 0;

  // Alias hit: an exact token match, or the whole path joined back together.
  const aliasTargets = new Set<string>(route.aliases ?? []);
  if (aliasTargets.size > 0) {
    const joined = inputTokens.join('-');
    if (aliasTargets.has(joined) || inputTokens.some((t) => aliasTargets.has(t))) {
      score = Math.max(score, 0.92);
    }
  }

  // Typo distance, measured on the most specific segment and on the whole path.
  const inputTail = inputTokens[inputTokens.length - 1] ?? '';
  const routeTail = routeTokens[routeTokens.length - 1] ?? '';
  if (routeTail) {
    score = Math.max(score, similarity(inputTail, routeTail));
    score = Math.max(
      score,
      similarity(inputTokens.join('-'), routeTokens.join('-')),
    );
  }

  // Token overlap, as a fraction of the route's own tokens.
  if (routeTokens.length > 0) {
    const shared = routeTokens.filter((t) => inputTokens.includes(t)).length;
    score = Math.max(score, (shared / routeTokens.length) * 0.85);
  }

  // Section prefix: the visitor found the right area, wrong page.
  if (normalizedHref !== '/' && normalizedInput.startsWith(`${normalizedHref}/`)) {
    score = Math.max(score, 0.8);
  }

  return Math.min(score, 0.99);
}

/**
 * Confidence floor for showing a guess.
 *
 * A wrong "did you mean" is worse than none: it sends the visitor down a
 * second dead end and costs the page its credibility. Tuned so `/princing`
 * resolves and `/qwertyuiop` does not.
 */
export const SUGGESTION_THRESHOLD = 0.62;

export interface RouteSuggestion extends NavigableRoute {
  /** 0-1 confidence that this is the route the visitor wanted. */
  score: number;
}

/** Best guesses for a requested path, most confident first. */
export function suggestRoutes(
  requestedPath: string | null | undefined,
  limit = 3,
): RouteSuggestion[] {
  if (!requestedPath) return [];

  const normalized = normalizePath(requestedPath);
  if (normalized === '/') return [];

  return NAVIGABLE_ROUTES
    .map((route) => ({ ...route, score: scoreRoute(route, normalized) }))
    .filter((route) => route.score >= SUGGESTION_THRESHOLD && route.href !== normalized)
    .sort((a, b) => b.score - a.score || b.weight - a.weight)
    .slice(0, limit);
}
