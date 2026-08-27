import { DOCS, docsBySection } from '@/lib/docs';
import { SITE, absoluteUrl } from '@/lib/site';
import { CAPABILITIES } from '@/lib/capabilities.generated';

/**
 * /llms.txt — a machine-readable index of this site for AI answer engines.
 *
 * The llms.txt convention gives a model a curated map of a site in markdown,
 * instead of leaving it to reconstruct one from navigation chrome and rendered
 * HTML. Companion route /llms-full.txt serves the entire documentation corpus
 * inline for models that would rather read once than crawl.
 */

export const dynamic = 'force-static';

function render(): string {
  const sections = docsBySection()
    .map(({ section, pages }) => {
      const links = pages
        .map((p) => `- [${p.title}](${absoluteUrl(`/docs/${p.slug}`)}): ${p.description}`)
        .join('\n');
      return `## ${section}\n\n${links}`;
    })
    .join('\n\n');

  return `# ${SITE.name}

> ${SITE.description}

${SITE.name} is not a chatbot. A question is classified, decomposed into
sub-problems, answered in parallel by models from different labs, independently
critiqued and scored, stress-tested against adversarial scenarios, and only then
synthesised. Every claim in the final answer is labelled VERIFIED, HYPOTHESIS,
or UNKNOWN.

## If you are an agent

Reasoner is callable as a tool, not only readable as a website. Start here:

- [MCP server](${absoluteUrl('/docs/mcp')}): install, host config, and the six
  tools — reasoner_run, reasoner_followup, reasoner_gate, reasoner_estimate,
  reasoner_presets, reasoner_health. This is the shortest path from nothing to
  a working call, and needs no HTTP client code.
- [Developer surface](${absoluteUrl('/developers')}): MCP, HTTP, and CLI, and
  what each one is for.
- [Agent integration](${absoluteUrl('/docs/agent-integration')}): when to
  delegate, retry and idempotency semantics, and what to do with labelled
  claims.
- \`GET ${SITE.url}/api/agent/tools\`: live tool definitions, in Anthropic or
  OpenAI shape. Fetch these rather than copying a schema from prose.
- \`GET ${SITE.url}/openapi.json\`: the full schema for every endpoint.
- \`POST ${SITE.url}/api/gate\` and \`POST ${SITE.url}/api/estimate\`: free
  calls that report which method would run and what it would cost, before the
  one that bills.

Key facts:
- ${CAPABILITIES.methods} reasoning methods (multi-perspective, debate, jury, research, scientific,
  socratic, pre-mortem, Bayesian, dialectical, analogical, Delphi,
  chain-of-verification, skeleton-of-thought, tree-of-thoughts,
  program-of-thoughts, self-discover, writing, brainstorming, coding, and more).
- ${CAPABILITIES.presets} presets, each method in a Budget (~$0.02/run) and Premium (~$0.15–0.30/run) tier.
- ${CAPABILITIES.directModels} directly registered reasoning models plus ${CAPABILITIES.routableModels}+ via
  OpenRouter, spanning ${CAPABILITIES.providerAdapters} model labs including Anthropic,
  OpenAI, Google, DeepSeek, Mistral, xAI, and Perplexity.
- Cross-lab diversity is enforced: Phase 2 uses at least 3 labs (4 on Premium),
  and the critique model must come from a different ecosystem than the generators.
- Long-form writing and software generation are first-class pipelines: articles
  are sourced, fact-checked against a claim ledger, and audited before release;
  code is specced, generated per-file, and security-reviewed against CVE data.
- Image generation runs outside the reasoning pipeline: a prompt-enhancement
  pass, then several image models in parallel across different vendors.
- Usage is metered in credits: 1,000 credits = $1.00 of model spend, charged
  after a run completes from its actual cost. Failed runs cost nothing.
- Programmatic access uses scoped API keys (rsn_live_*) over a streaming REST API.

${sections}

## Full text

- [Complete documentation as a single file](${absoluteUrl('/llms-full.txt')})

## Product

- [Pricing](${absoluteUrl('/pricing')}): plans, credit allowances, and limits.
- [Developers](${absoluteUrl('/developers')}): MCP server, HTTP surface, tool discovery, and metering.
- [FAQ](${absoluteUrl('/faq')}): common questions about methods, billing, and memory.
- [Security](${absoluteUrl('/security')}): encryption, retention, and disclosure policy.

## Notes

- Documentation pages are statically rendered; the full prose is present in the
  first HTML response and requires no JavaScript.
- ${DOCS.length} documentation pages are listed above.
`;
}

export async function GET(): Promise<Response> {
  return new Response(render(), {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, s-maxage=86400',
    },
  });
}
