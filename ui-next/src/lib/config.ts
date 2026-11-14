// Phase plan per method, read by the run card (components/chat/RunProgress).
// Generated from the backend flows; keyed by method name in kebab-case.
export { METHOD_PHASES } from './method-phases.generated';

/** Human-friendly descriptions for each reasoning method. */
export const METHOD_DESCRIPTIONS: Record<string, string> = {
  'multi-perspective': 'Analyzes your problem from multiple expert viewpoints simultaneously',
  'debate': 'Pits opposing arguments against each other and finds consensus',
  'jury': 'Multiple independent agents evaluate evidence and vote on a verdict',
  'research': 'Iterative web search with source verification and synthesis',
  'scientific': 'Generates hypotheses, designs falsification tests, and reports findings',
  'socratic': 'Asks probing questions to surface hidden assumptions and deepen understanding',
  'pre-mortem': 'Imagines failure scenarios and works backwards to prevent them',
  'bayesian': 'Updates beliefs probabilistically as new evidence arrives',
  'dialectical': 'Thesis → antithesis → synthesis through structured contradiction',
  'analogical': 'Maps your problem to a distant domain and transfers insights back',
  'delphi': 'Expert panels with iterative feedback and dissent surfacing',
  'cove': 'Drafts an answer, verifies claims, then revises based on evidence',
  'sot': 'Skeleton-of-thought: outlines first, then fills sections in parallel',
  'tot': 'Tree-of-thought: explores multiple reasoning branches and selects the best',
  'pot': 'Program-of-thought: writes and executes code to solve the problem',
  'self-discover': 'Self-discovers and adapts the best reasoning structure for your problem',
  'writing': 'Researches, outlines, drafts, fact-checks, and assembles a polished article',
  'brainstorming': 'Generates ideas, clusters them, and develops the most promising',
};

/** Example prompts shown in the centered empty-state composer. */
export const EXAMPLE_PROMPTS: string[] = [
  'Should I bootstrap or raise VC?',
  'What assumptions am I making about remote work?',
  'Should companies ban internal email?',
  'Why did our product launch fail?',
  'Can caffeine improve long-term memory?',
  'What does the evidence say about 4-day work weeks?',
  'How is building a startup like playing poker?',
  'Free will vs determinism — what survives scrutiny?',
  'What will the price of lithium be in 2030?',
];

export const API = {
  HEALTH: '/api/health',
  RUN: '/api/run',
  RUN_FOLLOWUP: '/api/run-followup',
  STOP: '/api/stop',
  CACHE: '/api/cache',
  PRESETS: '/api/presets',
  MODELS: '/api/models',
  ESTIMATE: '/api/estimate',
  GATE: '/api/gate',
  WEATHER: '/api/weather',
  STOCKS: '/api/stocks',
  CALCULATE: '/api/calculate',
  SEARCH: '/api/search',
  UPLOAD: '/api/upload',
  FEEDBACK: '/api/feedback',
  CONTACT: '/api/contact',
  ACCOUNT_DELETE: '/api/account/delete',
  QUOTA: '/api/quota',
  CREDITS: '/api/credits',
  CREDITS_LEDGER: '/api/credits/ledger',
  API_KEYS: '/api/account/api-keys',
  API_KEY_BY_ID: (id: string) => `/api/account/api-keys/${encodeURIComponent(id)}`,
  ERROR_REPORT: '/api/error-report',
  GENERATE_IMAGE: '/api/generate-image',
  NEURO_HEALTH: '/api/neuro/health',
  NEURO_SESSIONS: '/api/neuro/sessions',
  NEURO_RECALL: '/api/neuro/recall',
  NEURO_LEARN: '/api/neuro/learn',
  PIPELINE_RESUME: (id: string) => `/api/pipelines/${encodeURIComponent(id)}/resume-stream`,
  AGENT_RUN: '/api/agent/run',
  AGENT_RUN_SYNC: '/api/agent/run/sync',
  WEBSOCKET_TICKET: '/api/websocket/ticket',
  PROVENANCE_CAPABILITIES: '/api/provenance/capabilities',
  PROVENANCE_INSPECT: '/api/provenance/inspect',
  PROVENANCE_SCRUB: '/api/provenance/scrub',
  PROVENANCE_REWRITE: '/api/provenance/rewrite',
};

export const DEFAULTS = {
  tier: 'budget' as 'budget' | 'premium',
  topK: 2,
};

export const LIMITS = {
  imagePromptMaxChars: 4000,
  maxFileSizeBytes: 10 * 1024 * 1024,
  maxAttachments: 5,
  maxRecentCommands: 3,
  titleTruncateChars: 45,
  maxTagDisplay: 4,
  maxReferenceImages: 4,
  neuroSessionsLimit: 20,
  neuroRecallMaxResults: 5,
  webSearchNumResults: 10,
};

export const WS = {
  defaultUrl: 'ws://127.0.0.1:8003/ws',
  maxReconnectAttempts: 5,
  baseReconnectDelayMs: 1000,
};

export const PIPELINE_DEFAULTS = {
  method: 'multi_perspective',
  topK: 2,
  sequential: false,
  enhancePrompt: true,
  webSearch: false,
  smartSearch: true,
  imageGenPreset: 'budget' as 'budget' | 'premium',
  imageGenBudgetNumImages: 4,
};

export const STORAGE_KEYS = {
  appStore: 'ara-ui-store',
  featureFlags: 'ara-feature-flags',
};

/** Typography sizes per DESIGN.md hierarchy. */
export const TEXT_SIZES = {
  /** DESIGN.md Tiny — badges, fine print, source numbers. 11px, not 10:
      the token floor is set at the smallest size that stays readable. */
  tiny: 'text-[length:var(--text-2xs)]',
  /** Synthesis / final output — maps to DESIGN.md Body (~18px). */
  synthesis: 'text-[length:var(--text-md)] leading-relaxed',
  /** Intermediate phase cards — maps to DESIGN.md Nav/UI (15px). */
  phaseCard: 'text-[length:var(--text-sm)] leading-relaxed',
  /** Chat feed body — maps to DESIGN.md Body (18px). */
  body: 'text-[length:var(--text-md)]',
};

export const TIMING = {
  copiedFeedbackMs: 2000,
  streamingBounceDelays: [0, 150, 300] as const,
  serverStatusAbortTimeoutMs: 5000,
  serverStatusCheckIntervalMs: 10000,
  presetsRefreshIntervalMs: 60000,
  scrollAnchorThresholdPx: 120,
  durationFormatMsThreshold: 1000,
  estimateDebounceMs: 400,
  neuroLearnStatusClearMs: 3000,
  imageGenProgressDurationMs: 25000,
  imageGenProgressIntervalMs: 100,
  /** How long to wait for an OAuth redirect before assuming it never happened
   *  and handing the sign-in form back. On success the page is gone long
   *  before this; it only ever fires when the navigation was dropped. */
  oauthRedirectTimeoutMs: 15000,
  csrfMaxAgeSeconds: 60 * 60 * 24,
  jsonBodyMaxBytes: 1024 * 1024,
};
