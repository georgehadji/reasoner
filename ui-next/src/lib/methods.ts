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

/** The preset for a run: HyperGate's `auto-…` family, or the picked method's. */
export function presetFor(method: MethodSlug | null, westernOnly: boolean, tier: string): string {
  return `${method ?? 'auto'}-${westernOnly ? 'western-' : ''}${tier}`;
}
