import type { Metadata } from 'next';
import DevelopersPage from '@/components/landing/DevelopersPage';
import { JsonLd } from '@/components/seo/JsonLd';
import { breadcrumbSchema, howToSchema, webApiSchema } from '@/lib/schema';
import { SITE, absoluteUrl } from '@/lib/site';

/**
 * /developers — the marketing page for the programmatic surface.
 *
 * Carries more structured data than the other marketing routes on purpose.
 * The reader this page is written for is frequently not a person browsing but
 * a model answering "can I call this from an agent, and how" on someone's
 * behalf. A WebAPI node names the entry points, and a HowTo carries the three
 * real MCP setup steps, so an answer engine can quote the procedure instead of
 * paraphrasing the prose around it — and the citation it hands back lands on
 * /docs/mcp, which is where the full instructions live.
 */

export const metadata: Metadata = {
  title: 'Developers',
  description:
    'Call Reasoner from software: an MCP server with six tools, synchronous and streaming HTTP endpoints, a command-line entry point, live tool discovery, and answers whose every claim is labelled.',
  keywords: [
    'MCP server',
    'Model Context Protocol',
    'reasoning API',
    'agent tool use',
    'LLM orchestration API',
    'streaming SSE API',
    'AI agent integration',
    'headless reasoning CLI',
  ],
  alternates: {
    canonical: absoluteUrl('/developers'),
    types: {
      'text/plain': [
        { url: absoluteUrl('/llms.txt'), title: `${SITE.name} documentation index for LLMs` },
      ],
    },
  },
  openGraph: {
    title: `Developers — ${SITE.name}`,
    description:
      'MCP server, streaming and synchronous HTTP, a CLI, live tool discovery, and an answer your code can act on.',
    url: absoluteUrl('/developers'),
    type: 'website',
  },
};

const MCP_HOW_TO = howToSchema({
  name: 'Add Reasoner to an MCP host',
  description:
    'Install the Reasoner MCP server and expose its six reasoning tools to Claude Desktop, Claude Code, or any other Model Context Protocol host.',
  url: '/developers',
  steps: [
    {
      name: 'Install the MCP extra',
      text: 'Run `pip install "reasoner[mcp]"`, which adds the Model Context Protocol server to the Reasoner package.',
    },
    {
      name: 'Add the server to your host config',
      text: 'Register a stdio server in the host’s mcpServers block: command "python", args ["mcp_server.py"], and REASONER_API_KEY in env.',
    },
    {
      name: 'Call the tools',
      text: 'The host exposes reasoner_run, reasoner_followup, reasoner_gate, reasoner_estimate, reasoner_presets, and reasoner_health. The two paid tools report progress once per pipeline phase.',
    },
  ],
});

export default function Page() {
  return (
    <>
      <JsonLd
        data={[
          webApiSchema(),
          MCP_HOW_TO,
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'Developers', path: '/developers' },
          ]),
        ]}
      />
      <DevelopersPage />
    </>
  );
}
