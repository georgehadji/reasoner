'use client';

import { useQuota } from '@/hooks/useQuota';

export function UsageBadge() {
  const { quota } = useQuota();
  if (!quota) return null;

  const percent = (quota.used / quota.max) * 100;
  // --warn is reserved for epistemic labels — the near-limit tier still needs
  // a signal without it, so weight carries what colour used to: heavier ink,
  // not a hue, says "watch this."
  const tone =
    percent >= 90 ? 'text-[var(--red)] font-semibold' : percent >= 70 ? 'text-[var(--text)] font-semibold' : 'text-[var(--accent)]';

  return (
    <div className={`text-[length:var(--text-xs)] font-medium ${tone}`}>
      {quota.used} / {quota.max} queries
    </div>
  );
}
