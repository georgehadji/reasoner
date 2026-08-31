/**
 * Turns an inline epistemic label the pipeline writes into its own prose —
 * `[VERIFIED from team size data]`, `[HYPOTHESIS]`, `[UNKNOWN — no source
 * found]` — into a real element instead of literal square-bracket text.
 *
 * Independent of `demo-record.ts`'s `parseInline`/`parseSynthesis`: those are
 * unexported, argument-less, and scoped to the one captured run the landing
 * page renders. This is a remark plugin so it runs inside `MarkdownRenderer`,
 * which is what every *live* pipeline run — Perspectives phase, Synthesis,
 * every other phase's fallback markdown — renders through. Same three
 * `.epistemic-*` classes either way (`epistemicClassName` below), so a label
 * looks identical on the captured landing-page run and a live run.
 *
 * Walks `children` by hand rather than pulling in `unist-util-visit`: the
 * traversal here is one shape (recurse into `.children`, splice matched text
 * nodes in place), not worth a dependency for.
 */
import type { Parent, PhrasingContent, Root, Text } from 'mdast';

export type EpistemicLabelName = 'VERIFIED' | 'HYPOTHESIS' | 'UNKNOWN';

const LABEL_RE = /\[(VERIFIED|HYPOTHESIS|UNKNOWN)([^\]]*)\]/g;

/** Also doubles as the hast tag name `remarkEpistemic` emits — see
 *  `applyData`'s `hName` handling in mdast-util-to-hast — so the same string
 *  keys both the CSS class and the `MarkdownRenderer` component map. */
export const EPISTEMIC_TAG: Record<EpistemicLabelName, string> = {
  VERIFIED: 'epistemic-verified',
  HYPOTHESIS: 'epistemic-hypothesis',
  UNKNOWN: 'epistemic-unknown',
};

/** Shared with `Segments.tsx`'s landing-page marks so both surfaces render
 *  from one utility-class string. */
export function epistemicClassName(tag: string): string {
  return `${tag} ml-[var(--space-1)] pl-[var(--space-2)] font-sans text-[length:var(--text-2xs)] font-semibold uppercase tracking-[var(--tracking-label)]`;
}

/** mdast has no built-in node type for this — `data.hName`/`data.hChildren`
 *  is the documented escape hatch mdast-util-to-hast reads for exactly this
 *  case, but nothing in `@types/mdast` describes the resulting node shape. */
interface EpistemicMarkNode {
  type: 'epistemicMark';
  data: { hName: string; hChildren: [Text] };
}

function splitLabels(node: Text): PhrasingContent[] | null {
  LABEL_RE.lastIndex = 0;
  if (!LABEL_RE.test(node.value)) return null;
  LABEL_RE.lastIndex = 0;

  const out: PhrasingContent[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = LABEL_RE.exec(node.value))) {
    if (match.index > cursor) {
      out.push({ type: 'text', value: node.value.slice(cursor, match.index) });
    }
    const label = match[1] as EpistemicLabelName;
    const qualifier = match[2].trim();
    const text = qualifier ? `${label} ${qualifier}` : label;
    const mark: EpistemicMarkNode = {
      type: 'epistemicMark',
      data: { hName: EPISTEMIC_TAG[label], hChildren: [{ type: 'text', value: text }] },
    };
    out.push(mark as unknown as PhrasingContent);
    cursor = match.index + match[0].length;
  }
  if (cursor < node.value.length) {
    out.push({ type: 'text', value: node.value.slice(cursor) });
  }
  return out;
}

function walk(node: Parent): void {
  for (let i = node.children.length - 1; i >= 0; i--) {
    const child = node.children[i];
    if (child.type === 'text') {
      const replacement = splitLabels(child as Text);
      if (replacement) node.children.splice(i, 1, ...replacement);
    } else if ('children' in child) {
      walk(child as unknown as Parent);
    }
  }
}

/** Marks populate once a phase's full markdown reaches `MarkdownRenderer` —
 *  during active SSE streaming, `ChatFeed` renders raw text directly and
 *  never calls this (see `StreamingMarkdown.tsx`'s docblock), so a label can
 *  never be split across two chunks here. */
export function remarkEpistemic() {
  return (tree: Root) => {
    walk(tree as unknown as Parent);
  };
}

/** Same match, without going through the mdast tree — for a summary (a
 *  count, a gutter list) alongside prose that renders through
 *  `MarkdownRenderer` separately rather than through this plugin's output. */
export function extractEpistemicMarks(
  text: string,
): Array<{ label: EpistemicLabelName; qualifier: string }> {
  const marks: Array<{ label: EpistemicLabelName; qualifier: string }> = [];
  LABEL_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = LABEL_RE.exec(text))) {
    marks.push({ label: match[1] as EpistemicLabelName, qualifier: match[2].trim() });
  }
  return marks;
}
