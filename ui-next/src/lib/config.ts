import { MethodPhase } from './types';

// Phase timeline labels per method — still used by PhaseTimeline component.
// Keyed by the method name that the backend echoes in the SSE start event
// as `auto_selected_method` (snake_case) or derived from the effective preset.
export const METHOD_PHASES: Record<string, MethodPhase[]> = {
  'multi-perspective': [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Perspectives', short: 'Analyze' },
    { id: 3, name: 'Critique', short: 'Critique' },
    { id: 4, name: 'Stress Testing', short: 'Stress' },
    { id: 5, name: 'Synthesis', short: 'Synthesize' },
  ],
  debate: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Opening', short: 'Opening' },
    { id: 3, name: 'Rebuttals', short: 'Rebuttal' },
    { id: 4, name: 'Verdict', short: 'Verdict' },
    { id: 5, name: 'Synthesis', short: 'Synthesize' },
  ],
  jury: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Generation', short: 'Generate' },
    { id: 3, name: 'Critique', short: 'Critique' },
    { id: 4, name: 'Verification', short: 'Verify' },
    { id: 5, name: 'Verdict', short: 'Verdict' },
  ],
  research: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Search', short: 'Search' },
    { id: 3, name: 'Analysis', short: 'Analyze' },
    { id: 4, name: 'Verification', short: 'Verify' },
    { id: 5, name: 'Report', short: 'Report' },
  ],
  scientific: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Hypotheses', short: 'Hypothesize' },
    { id: 3, name: 'Falsification', short: 'Falsify' },
    { id: 4, name: 'Stress Testing', short: 'Stress' },
    { id: 5, name: 'Theory', short: 'Theory' },
  ],
  socratic: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Questions', short: 'Question' },
    { id: 3, name: 'Answers', short: 'Answer' },
    { id: 4, name: 'Conclusion', short: 'Conclude' },
  ],
  'pre-mortem': [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Failure Modes', short: 'Failures' },
    { id: 3, name: 'Backtrack', short: 'Backtrack' },
    { id: 4, name: 'Signals', short: 'Signals' },
    { id: 5, name: 'Redesign', short: 'Redesign' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  bayesian: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Priors', short: 'Priors' },
    { id: 3, name: 'Likelihood', short: 'Likelihood' },
    { id: 4, name: 'Posterior', short: 'Posterior' },
    { id: 5, name: 'Sensitivity', short: 'Sensitivity' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  dialectical: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Thesis', short: 'Thesis' },
    { id: 3, name: 'Antithesis', short: 'Antithesis' },
    { id: 4, name: 'Contradictions', short: 'Contradict' },
    { id: 5, name: 'Aufhebung', short: 'Aufhebung' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  analogical: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Abstraction', short: 'Abstract' },
    { id: 3, name: 'Domain Search', short: 'Search' },
    { id: 4, name: 'Mapping', short: 'Map' },
    { id: 5, name: 'Transfer', short: 'Transfer' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  delphi: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Round 1', short: 'R1' },
    { id: 3, name: 'Aggregation', short: 'Aggregate' },
    { id: 4, name: 'Round 2', short: 'R2' },
    { id: 5, name: 'Convergence', short: 'Converge' },
    { id: 6, name: 'Dissent', short: 'Dissent' },
    { id: 7, name: 'Synthesis', short: 'Synthesize' },
  ],
  cove: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Draft', short: 'Draft' },
    { id: 3, name: 'Verify', short: 'Verify' },
    { id: 4, name: 'Answer', short: 'Answer' },
    { id: 5, name: 'Revise', short: 'Revise' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  sot: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Skeleton', short: 'Skeleton' },
    { id: 3, name: 'Parallel Solve', short: 'Solve' },
    { id: 4, name: 'Assemble', short: 'Assemble' },
    { id: 5, name: 'Synthesis', short: 'Synthesize' },
  ],
  tot: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Decompose', short: 'Decompose' },
    { id: 3, name: 'Generate', short: 'Generate' },
    { id: 4, name: 'Evaluate', short: 'Evaluate' },
    { id: 5, name: 'Select', short: 'Select' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  pot: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Code Gen', short: 'Code' },
    { id: 3, name: 'Execute', short: 'Execute' },
    { id: 4, name: 'Interpret', short: 'Interpret' },
    { id: 5, name: 'Synthesis', short: 'Synthesize' },
  ],
  'self-discover': [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 1.5, name: 'Deep Read', short: 'Read' },
    { id: 2, name: 'Select Modules', short: 'Select' },
    { id: 3, name: 'Adapt', short: 'Adapt' },
    { id: 4, name: 'Execute', short: 'Execute' },
    { id: 5, name: 'Reflect', short: 'Reflect' },
    { id: 6, name: 'Synthesis', short: 'Synthesize' },
  ],
  writing: [
    { id: 0, name: 'Classification', short: 'Classify' },
    { id: 1, name: 'Decomposition', short: 'Decompose' },
    { id: 2, name: 'Decompose Topic', short: 'Topic' },
    { id: 2.5, name: 'Retrieve Sources', short: 'Sources' },
    { id: 3, name: 'Extract Claims (CoVE)', short: 'Claims' },
    { id: 3.5, name: 'Adversarial Verify', short: 'Verify' },
    { id: 4, name: 'Synthesize (SoT)', short: 'Synthesize' },
    { id: 4.25, name: 'Pre-Mortem', short: 'Pre-Mortem' },
    { id: 4.5, name: 'Journal Review', short: 'Review' },
    { id: 5, name: 'Final Assembly', short: 'Assembly' },
  ],
};

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
  /** DESIGN.md Tiny (10px) — badges, fine print, source numbers. */
  tiny: 'text-[10px]',
  /** Synthesis / final output — maps to DESIGN.md Body (~18px). */
  synthesis: 'text-[17px] leading-relaxed',
  /** Intermediate phase cards — maps to DESIGN.md Nav/UI (15px). */
  phaseCard: 'text-[15px] leading-relaxed',
  /** Chat feed body — maps to DESIGN.md Body (18px). */
  body: 'text-[18px]',
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
