import type { SynthesisReliability, SynthesisScope } from '@/lib/types';

const COUNTRY_NAMES: Record<string, string> = {
  GR: 'Greece',
  US: 'United States',
  GB: 'United Kingdom',
  DE: 'Germany',
  FR: 'France',
  CY: 'Cyprus',
  EU: 'European Union',
};

export function scopeLine(scope: SynthesisScope | undefined): string | null {
  if (!scope?.as_of) return null;
  const code = scope.jurisdiction?.trim().toUpperCase();
  const where = code ? COUNTRY_NAMES[code] ?? code : 'country not stated';
  return `Scope: ${where} · as of ${scope.as_of}`;
}

export function ScopeLine({ scope }: { scope?: SynthesisScope }) {
  const line = scopeLine(scope);
  if (!line) return null;
  return <p className="mb-[var(--space-2)] text-[length:var(--text-xs)] text-[var(--text-muted)]">{line}</p>;
}

/** Nothing for "answer" or an empty report; otherwise a caution or a refer-out notice. */
export function ReliabilityBanner({ reliability }: { reliability?: SynthesisReliability }) {
  const level = reliability?.level;
  if (level !== 'answer_with_caveats' && level !== 'refer') return null;
  const refer = level === 'refer';
  const reasons = (reliability?.reasons ?? []).filter((r) => typeof r === 'string' && r);
  return (
    <div
      role={refer ? 'alert' : 'note'}
      className={`mb-[var(--space-4)] rounded-[var(--radius-lg)] border p-4 ${
        refer
          ? 'border-[var(--red-border)] bg-[var(--red-bg)] text-[var(--red)]'
          : 'border-[var(--border-strong)] bg-[var(--surface-2)] text-[var(--unknown)]'
      }`}
    >
      <p className="text-[length:var(--text-sm)] font-semibold">
        {refer ? 'Check with a professional' : 'Use with caution'}
      </p>
      <p className="mt-1 text-[length:var(--text-sm)] text-[var(--text)]">
        {refer
          ? 'This answer is not reliable enough to act on by itself.'
          : 'This answer comes with limits you should know about.'}
      </p>
      {reasons.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-[length:var(--text-sm)] text-[var(--text)]">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
