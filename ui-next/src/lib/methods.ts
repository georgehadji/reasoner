/**
 * Reasoning methods the user can pick in the composer instead of letting
 * HyperGate choose. Each slug is the preset family's prefix in
 * domain/preset_registry.py: the run sends `<slug>[-western]-<tier>`, and
 * every method listed here has all four of those presets
 * (tests/unit/test_ui_method_presets.py fails if one is missing).
 *
 * Not listed: image-gen (the composer's Image toggle) and subagent (an
 * internal delegation method, not something to ask a question with).
 */
export const METHOD_OPTIONS = [
  { slug: 'multi-perspective', label: 'Multi-Perspective' },
  { slug: 'debate', label: 'Debate' },
  { slug: 'jury', label: 'Jury' },
  { slug: 'research', label: 'Research' },
  { slug: 'scientific', label: 'Scientific' },
  { slug: 'socratic', label: 'Socratic' },
  { slug: 'pre-mortem', label: 'Pre-Mortem' },
  { slug: 'bayesian', label: 'Bayesian' },
  { slug: 'dialectical', label: 'Dialectical' },
  { slug: 'analogical', label: 'Analogical' },
  { slug: 'delphi', label: 'Delphi' },
  { slug: 'cove', label: 'Chain-of-Verification' },
  { slug: 'sot', label: 'Skeleton-of-Thought' },
  { slug: 'tot', label: 'Tree-of-Thoughts' },
  { slug: 'pot', label: 'Program-of-Thoughts' },
  { slug: 'self-discover', label: 'Self-Discover' },
  { slug: 'iterative-critique', label: 'Iterative Critique' },
  { slug: 'self-refine', label: 'Self-Refine' },
  { slug: 'brainstorming', label: 'Brainstorming' },
  { slug: 'writing', label: 'Writing' },
  { slug: 'article', label: 'Article' },
  { slug: 'coding', label: 'Coding' },
  { slug: 'cross-language', label: 'Cross-Language' },
] as const;

export type MethodSlug = (typeof METHOD_OPTIONS)[number]['slug'];

/**
 * Menu order per tier, cheapest first, by the backend's per-run estimate
 * (spend_limit_service.estimate_run_cost of `<slug>-<tier>`). The two tiers
 * route to different models, so their orders differ. The estimate counts one
 * call per role: looping methods (self-refine, iterative-critique) can cost
 * more than their place suggests. tests/unit/test_ui_method_presets.py fails
 * when prices change the order.
 */
export const METHOD_ORDER_BY_COST: Record<'budget' | 'premium', readonly MethodSlug[]> = {
  budget: [
    'sot', 'pot', 'pre-mortem', 'socratic', 'dialectical', 'analogical', 'cove', 'tot',
    'self-discover', 'cross-language', 'delphi', 'self-refine', 'jury', 'scientific',
    'brainstorming', 'bayesian', 'debate', 'iterative-critique', 'multi-perspective',
    'coding', 'writing', 'research', 'article',
  ],
  premium: [
    'sot', 'pot', 'scientific', 'analogical', 'self-refine', 'pre-mortem', 'cove', 'tot',
    'self-discover', 'socratic', 'dialectical', 'bayesian', 'delphi', 'research',
    'brainstorming', 'debate', 'iterative-critique', 'jury', 'multi-perspective', 'coding',
    'writing', 'cross-language', 'article',
  ],
};

/** The menu for *tier*, cheapest method first. */
export function methodsByCost(tier: string) {
  const order = METHOD_ORDER_BY_COST[tier === 'premium' ? 'premium' : 'budget'];
  return [...METHOD_OPTIONS].sort((a, b) => order.indexOf(a.slug) - order.indexOf(b.slug));
}

/** The preset for a run: HyperGate's `auto-…` family, or the picked method's. */
export function presetFor(method: MethodSlug | null, westernOnly: boolean, tier: string): string {
  return `${method ?? 'auto'}-${westernOnly ? 'western-' : ''}${tier}`;
}
