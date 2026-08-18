import type { ProvenanceCharHit, SynthesisProvenanceReport } from './types';

/** Extract `data.provenance_report` from a synthesis phase's SSE payload.
 *
 * Mirrors the narrow-then-return-null shape of `getSynthesisSections` in
 * `components/phases/PhaseRenderer.tsx` -- `data` is always `unknown` here
 * since it comes straight off the wire.
 */
export function getProvenanceReport(data: unknown): SynthesisProvenanceReport | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as Record<string, unknown>;
  const report = d.provenance_report;
  if (!report || typeof report !== 'object') return null;
  const r = report as Record<string, unknown>;
  const core = r.core_solution as Record<string, unknown> | null | undefined;
  return {
    core_solution: core
      ? {
          length: typeof core.length === 'number' ? core.length : 0,
          suspicious_total: typeof core.suspicious_total === 'number' ? core.suspicious_total : 0,
          hits: Array.isArray(core.hits) ? (core.hits as ProvenanceCharHit[]) : [],
          notes: Array.isArray(core.notes) ? (core.notes as string[]) : [],
        }
      : null,
    critical_insights_removed: typeof r.critical_insights_removed === 'number' ? r.critical_insights_removed : 0,
    action_blueprint_removed: typeof r.action_blueprint_removed === 'number' ? r.action_blueprint_removed : 0,
    open_questions_removed: typeof r.open_questions_removed === 'number' ? r.open_questions_removed : 0,
  };
}

/** Total carriers removed across every scrubbed field in a synthesis report. */
export function totalRemoved(report: SynthesisProvenanceReport): number {
  return (
    (report.core_solution?.suspicious_total ?? 0) +
    report.critical_insights_removed +
    report.action_blueprint_removed +
    report.open_questions_removed
  );
}
