/**
 * Answer-first presentation of a finished run.
 *
 * A run's phases arrive in pipeline order, so the answer (the synthesis, or
 * the final article) used to be the last of five to eleven cards. These pure
 * helpers pick the answer out, say in one line what every other phase found,
 * and give the answer alone as Markdown for Copy and Download. Nothing here
 * calls a model: every figure is read from the phase payloads already sent.
 */
import { buildMarkdownFromPhase } from './markdown';

export interface PhaseLike {
  index: number;
  phase: number;
  name: string;
  data: unknown;
}

export interface FoundAnswer<P extends PhaseLike = PhaseLike> {
  kind: 'synthesis' | 'article';
  answer: P;
  /** Every other phase, in pipeline order. */
  process: P[];
}

type Rec = Record<string, unknown>;

const isRec = (v: unknown): v is Rec => typeof v === 'object' && v !== null && !Array.isArray(v);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

export function isSynthesisPhaseName(name: string): boolean {
  return /synthesis|report|theory|conclusion|verdict|redesign|aufhebung|transfer/i.test(name);
}

/** The run's article text; the humanize pass runs after final assembly and supersedes it. */
export function finalArticle(data: unknown): string | null {
  if (!isRec(data) || !isRec(data.writing_state)) return null;
  const ws = data.writing_state;
  for (const article of [ws.humanized_article, ws.final_article]) {
    if (typeof article === 'string' && article.trim()) return article;
  }
  return null;
}

/* What each method's final phase answers with: the branches of the backend's
   Phase 5 serializer (application/services/serializers.py `_ser_5` and
   `_ser_synthesis`). A phase named "Synthesis" that carries none of these
   has no answer to show, so it is not one. */
const ANSWER_KEYS = [
  'core_solution',
  'action_blueprint',
  'revised_answer',
  'hardened_solution',
  'sensitivity_results',
  'aufhebung',
  'transferred_solution',
  'backtrack_decision',
  'convergence',
  'dissent_report',
  'final_files',
];

const filled = (v: unknown): boolean =>
  typeof v === 'string' ? v.trim() !== '' : Array.isArray(v) ? v.length > 0 : isRec(v) ? Object.keys(v).length > 0 : v != null;

function carriesAnswer(data: unknown): boolean {
  if (!isRec(data)) return false;
  const scopes = [data, ...Object.entries(data).filter(([k, v]) => k.endsWith('_state') && isRec(v)).map(([, v]) => v as Rec)];
  return scopes.some((scope) => ANSWER_KEYS.some((key) => filled(scope[key])));
}

function lastIndex<P>(items: P[], test: (p: P) => boolean): number {
  for (let i = items.length - 1; i >= 0; i--) if (test(items[i])) return i;
  return -1;
}

/**
 * The phase to show first, or null when the run should keep pipeline order:
 * no answer phase, or the answer is the only phase (nothing to collapse).
 * An article outranks any synthesis-like phase (a fact-check report can follow
 * it), and within a kind the last match wins, since a later answer supersedes
 * an earlier one.
 */
export function findAnswer<P extends PhaseLike>(phases: P[]): FoundAnswer<P> | null {
  if (phases.length < 2) return null;
  let kind: FoundAnswer['kind'] = 'article';
  let i = lastIndex(phases, (p) => finalArticle(p.data) !== null);
  if (i < 0) {
    kind = 'synthesis';
    i = lastIndex(phases, (p) => carriesAnswer(p.data));
  }
  if (i < 0) return null;
  return { kind, answer: phases[i], process: phases.filter((_, j) => j !== i) };
}

const SINGULAR: Record<string, string> = { hypotheses: 'hypothesis', analyses: 'analysis', theses: 'thesis' };

function plural(n: number, word: string): string {
  if (n === 1) return `1 ${SINGULAR[word] ?? word.replace(/s$/, '')}`;
  return `${n} ${word}`;
}

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function modelsOf(data: unknown): string[] {
  if (!isRec(data)) return [];
  const listed = arr(data.models).filter((m): m is string => typeof m === 'string');
  const used = arr(data.candidates)
    .map((c) => (isRec(c) ? c.model_used : undefined))
    .filter((m): m is string => typeof m === 'string');
  return [...listed, ...used];
}

/* Keys that describe how a phase ran, not what it found. */
const META_KEYS = new Set(['tokens', 'models', 'subagents', 'errors', 'citations', 'quality', 'status', 'duration']);

function countLists(rec: Rec): string[] {
  return Object.entries(rec)
    .filter(([key, v]) => !META_KEYS.has(key) && Array.isArray(v) && v.length > 0)
    .map(([key, v]) => plural((v as unknown[]).length, key.replace(/_/g, ' ')));
}

/** One line saying what a phase found, or null when nothing is countable. */
export function summarizePhase(p: PhaseLike): string | null {
  const d = p.data;
  if (!isRec(d)) return null;

  if (typeof d.task_type === 'string') {
    return [d.task_type, typeof d.language === 'string' ? d.language : null].filter(Boolean).join(' · ');
  }
  const subProblems = arr(d.sub_problems);
  if (subProblems.length) {
    const assumptions = arr(d.assumptions).length;
    return [plural(subProblems.length, 'sub-problems'), assumptions ? plural(assumptions, 'assumptions') : null]
      .filter(Boolean)
      .join(' · ');
  }
  const vetted = arr(d.vetted_context);
  if (vetted.length) return `${plural(vetted.length, 'sources')} vetted`;

  const candidates = arr(d.candidates);
  if (candidates.length) {
    const labs = new Set(modelsOf({ candidates })).size;
    const head = plural(candidates.length, 'perspectives');
    return labs ? `${head} from ${plural(labs, 'models')}` : head;
  }
  const scores = arr(d.scores)
    .map((s) => (isRec(s) ? (s.total ?? s.score) : undefined))
    .filter((s): s is number => typeof s === 'number');
  if (scores.length) return `${scores.length} scored, top ${Math.max(...scores).toFixed(1)}/10`;

  if (isRec(d.writing_state)) {
    const ws = d.writing_state;
    const article = finalArticle(d);
    if (article) return plural(countWords(article), 'words');
    if (arr(ws.outline).length) return plural(arr(ws.outline).length, 'outline sections');
    if (arr(ws.factcheck_reviews).length) return plural(arr(ws.factcheck_reviews).length, 'fact-check reviews');
  }

  // Method-specific phases carry their findings in a `<method>_state` object
  // (or a top-level list such as debate_rounds); count what is there.
  const nested = Object.entries(d)
    .filter(([key, v]) => key.endsWith('_state') && isRec(v))
    .flatMap(([, v]) => countLists(v as Rec));
  const found = [...nested, ...countLists(d)].slice(0, 2);
  return found.length ? found.join(' · ') : null;
}

function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function sourcesOf(data: unknown): number {
  if (!isRec(data)) return 0;
  const cited = isRec(data.writing_state) ? arr(data.writing_state.sources_cited).length : 0;
  return arr(data.sources).length + cited;
}

/** "6 phases · 4 models · 3 sources · 2m 41s · $0.06" — parts with no data are left out. */
export function summarizeRun(phases: PhaseLike[], run: { duration?: number; cost?: number } = {}): string {
  const models = new Set(phases.flatMap((p) => modelsOf(p.data))).size;
  const sources = phases.reduce((n, p) => n + sourcesOf(p.data), 0);
  const parts = [
    plural(phases.length, 'phases'),
    models ? plural(models, 'models') : null,
    sources ? plural(sources, 'sources') : null,
    run.duration && run.duration > 0 ? formatDuration(run.duration) : null,
    run.cost && run.cost > 0 ? (run.cost < 0.01 ? '<$0.01' : `$${run.cost.toFixed(2)}`) : null,
  ];
  return parts.filter(Boolean).join(' · ');
}

function sourceLines(sources: unknown[]): string[] {
  return sources.flatMap((s) => {
    if (typeof s === 'string') return [`- ${s}`];
    if (isRec(s) && typeof s.url === 'string') {
      return [`- [${typeof s.title === 'string' && s.title ? s.title : s.url}](${s.url})`];
    }
    return [];
  });
}

/** The answer alone, as Markdown: what "Copy answer" and the download carry. */
export function answerMarkdown(found: FoundAnswer): string {
  const { answer } = found;
  if (found.kind === 'article') {
    const ws = (answer.data as Rec).writing_state as Rec;
    const lines = sourceLines(arr(ws.sources_cited));
    const body = (finalArticle(answer.data) ?? '').trim();
    return lines.length ? `${body}\n\n## Sources\n\n${lines.join('\n')}\n` : `${body}\n`;
  }
  const data = isRec(answer.data) ? { ...answer.data, models: undefined } : answer.data;
  return buildMarkdownFromPhase(answer.index, answer.phase, answer.name, data, {
    omitSections: ['vetted_context'],
    omitHeading: true,
  }).trim() + '\n';
}

/** Same rule MarkdownRenderer uses for heading ids, so links land. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

function plainText(md: string): string {
  return md
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`~]/g, '')
    .trim();
}

/** The h2/h3 outline of a Markdown document, skipping fenced code. */
export function extractHeadings(md: string): Array<{ level: 2 | 3; text: string; id: string }> {
  const out: Array<{ level: 2 | 3; text: string; id: string }> = [];
  let fenced = false;
  for (const line of md.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) {
      fenced = !fenced;
      continue;
    }
    if (fenced) continue;
    const m = /^(#{2,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!m) continue;
    const text = plainText(m[2]);
    if (text) out.push({ level: m[1].length as 2 | 3, text, id: slugify(text) });
  }
  return out;
}
