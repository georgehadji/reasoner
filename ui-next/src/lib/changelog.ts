/**
 * Changelog content.
 *
 * Every entry must trace to a dated commit on main, named in `commit`.
 * Work on an unmerged branch has not shipped and does not belong here,
 * nor does aspirational or in-progress work. Dates are the day the commit
 * (or the merge, for a pull request) landed on main.
 *
 * Extended 2026-11-14: the list had stopped at 2026-08-16 while nine
 * user-facing changes landed after it.
 */

export interface ChangelogEntry {
  date: string; // YYYY-MM-DD
  title: string;
  description: string;
  commit: string; // short hash on main
}

export const CHANGELOG: readonly ChangelogEntry[] = [
  {
    date: '2026-11-14',
    title: 'The contact form sends',
    description:
      'It used to show "Message sent" and send nothing. Messages now go by email, and the form says so when delivery fails.',
    commit: 'fe802db3',
  },
  {
    date: '2026-11-14',
    title: '/status reads the live health check',
    description:
      'The page always read as a disruption because its proxy called the wrong endpoint. It now shows each check the API runs, refreshed every 30 seconds.',
    commit: 'a4121730',
  },
  {
    date: '2026-11-14',
    title: 'Health check keeps its errors private',
    description:
      'A failed check used to show its raw error to anyone. The public response now gives only the status; admins still see the reason.',
    commit: '10b490ef',
  },
  {
    date: '2026-11-14',
    title: '/subprocessors lists every service a run reaches',
    description:
      'It named only the eight direct fallbacks. It now lists OpenRouter, every model maker in the registry, and the search, sign-in, payment, email and error-report services.',
    commit: '2bcf6066',
  },
  {
    date: '2026-11-14',
    title: 'Security claims the code does not back, removed',
    description:
      'Settings, the docs and the FAQ claimed end-to-end encryption, AES-256-GCM at rest, an internal PKI and configurable retention. None held, so the claims are gone.',
    commit: 'e04a046d',
  },
  {
    date: '2026-11-14',
    title: 'The public site, rebuilt',
    description: 'Every marketing page was rebuilt, with pages for regulated sectors and one for each policy.',
    commit: '0cf5d188',
  },
  {
    date: '2026-11-14',
    title: 'Escape no longer stops a run',
    description:
      'Closing the shortcuts panel, the image lightbox or the command palette with Escape also stopped the run. Escape now closes only the open dialog.',
    commit: 'ca22d266',
  },
  {
    date: '2026-11-13',
    title: 'Western-only presets',
    description:
      'Every method gained a twin that routes only to US and EU models. A request can also ask for it with western_only.',
    commit: 'c6264802',
  },
  {
    date: '2026-11-11',
    title: 'The answer comes first',
    description: 'A finished run shows its answer at the top, with the process collapsed below it.',
    commit: '702871aa',
  },
  {
    date: '2026-09-25',
    title: 'HyperGate routes in one call',
    description:
      'A single classifier call now decides the route. The LLM sub-agents run only when it times out, fails or is not confident.',
    commit: '2bfcfd35',
  },
  {
    date: '2026-09-07',
    title: 'Free model tiers removed',
    description:
      'OpenRouter withdraws :free models without notice, and six had already failed in production. No preset routes to one now.',
    commit: '34ea4bac',
  },
  {
    date: '2026-09-03',
    title: 'Added Claude Fable 5.1 and Gemini 3.8 Flash',
    description: 'Two new models in the registry, and the OpenRouter catalogue refreshed.',
    commit: 'b00fb1ba',
  },
  {
    date: '2026-08-29',
    title: 'Critique scores in the app',
    description: 'The critique phase shows its score table on /chat.',
    commit: '80e36b8d',
  },
  {
    date: '2026-08-27',
    title: 'A page for developers',
    description: 'Published /developers: the MCP server, the HTTP endpoints and the command line, on the site.',
    commit: '760d7724',
  },
  {
    date: '2026-08-26',
    title: 'Recalled memory kept out of instructions',
    description:
      'Memory recalled from earlier runs reaches a prompt only as wrapped user content, labelled with where it came from.',
    commit: 'a2e1807c',
  },
  {
    date: '2026-08-21',
    title: 'One model per phase',
    description:
      'No preset serves two of its phases from the same model, judged on the model actually served rather than its alias.',
    commit: '4829ddd2',
  },
  {
    date: '2026-08-18',
    title: 'Presets moved to current-generation models',
    description: 'Preset phases that ran on older models now route to current-generation ones.',
    commit: '60c58269',
  },
  {
    date: '2026-08-17',
    title: 'Code runs in a container',
    description: 'In production, generated code runs in an isolated container instead of a subprocess.',
    commit: '760d856b',
  },
  {
    date: '2026-08-16',
    title: 'Agent-native API, encryption v2, redesigned landing page',
    description:
      'Added a bearer-key agent API surface for programmatic access, upgraded session encryption, and rebuilt the marketing site on the current design system.',
    commit: '39c98ed8',
  },
  {
    date: '2026-08-14',
    title: 'Docs site, prepaid credits, user API keys',
    description:
      'Published the documentation site, moved billing to a prepaid credit model, and added self-serve API key management in Settings.',
    commit: 'f3cd4c6d',
  },
  {
    date: '2026-08-05',
    title: 'Brave Search for image and video results',
    description: 'Replaced the previous self-hosted search backend with Brave Search for image and video widgets.',
    commit: '382f2955',
  },
  {
    date: '2026-08-05',
    title: 'Added Qwen 3.8 Max and Qwen Image 3',
    description: 'Expanded the model registry with two new Qwen releases.',
    commit: 'bb16d29a',
  },
  {
    date: '2026-08-01',
    title: 'Model registry refresh',
    description: 'Added newly released OpenRouter models and fixed six dead model aliases.',
    commit: '86153c1f',
  },
  {
    date: '2026-07-18',
    title: 'Redis to Valkey migration',
    description: 'Migrated caching and rate-limiting infrastructure from Redis to Valkey.',
    commit: 'bd109494',
  },
] as const;
