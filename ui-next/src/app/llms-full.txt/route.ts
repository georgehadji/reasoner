import { DOCS } from '@/lib/docs';
import { SITE, absoluteUrl } from '@/lib/site';

/**
 * /llms-full.txt — the entire documentation corpus as one markdown file.
 *
 * Answer engines that ingest a whole document get better grounding than ones
 * stitching together fragments from separate crawls, and a single file removes
 * any dependency on rendering or navigation.
 */

export const dynamic = 'force-static';

function render(): string {
  const body = DOCS.map(
    (doc) =>
      `# ${doc.title}\n\n` +
      `Source: ${absoluteUrl(`/docs/${doc.slug}`)}\n` +
      `Section: ${doc.section}\n\n` +
      `${doc.description}\n${doc.body.trim()}`,
  ).join('\n\n---\n\n');

  return `# ${SITE.name} — complete documentation

> ${SITE.description}

Generated from ${absoluteUrl('/docs')}. Each section below corresponds to one
documentation page and links back to its canonical URL.

---

${body}
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
