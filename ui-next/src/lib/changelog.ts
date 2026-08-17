/**
 * Changelog content.
 *
 * A dated, moving changelog is one of the clearest "this is actively
 * maintained" signals a site can give — more convincing than any badge.
 * Every entry here must trace to a real, dated commit; this is not the
 * place for aspirational or in-progress work. See git log for the source
 * of truth this was backfilled from.
 */

export interface ChangelogEntry {
  date: string; // YYYY-MM-DD
  title: string;
  description: string;
}

export const CHANGELOG: readonly ChangelogEntry[] = [
  {
    date: '2026-08-16',
    title: 'Agent-native API, encryption v2, redesigned landing page',
    description:
      'Added a bearer-key agent API surface for programmatic access, upgraded session encryption, and rebuilt the marketing site on the current design system.',
  },
  {
    date: '2026-08-14',
    title: 'Docs site, prepaid credits, user API keys',
    description:
      'Published the documentation site, moved billing to a prepaid credit model, and added self-serve API key management in Settings.',
  },
  {
    date: '2026-08-05',
    title: 'Brave Search for image and video results',
    description: 'Replaced the previous self-hosted search backend with Brave Search for image and video widgets.',
  },
  {
    date: '2026-08-05',
    title: 'Added Qwen 3.8 Max and Qwen Image 3',
    description: 'Expanded the model registry with two new Qwen releases.',
  },
  {
    date: '2026-08-01',
    title: 'Model registry refresh',
    description: 'Added newly released OpenRouter models and fixed six dead model aliases.',
  },
  {
    date: '2026-07-18',
    title: 'Redis to Valkey migration',
    description: 'Migrated caching and rate-limiting infrastructure from Redis to Valkey.',
  },
] as const;
