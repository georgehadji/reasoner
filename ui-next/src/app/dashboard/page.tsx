'use client';

import { useEffect, useState, Suspense } from 'react';
import { apiFetch } from '@/lib/api-client';
import Link from 'next/link';
import { useCredits } from '@/hooks/useCredits';
import { useQuota } from '@/hooks/useQuota';
import { useSubscription } from '@/hooks/useSubscription';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

interface HistoryEntry {
  timestamp: string;
  tokens?: { total?: number };
}

function isValidPortalUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && u.hostname.endsWith('.stripe.com');
  } catch {
    return false;
  }
}

function StatCardSkeleton() {
  return (
    <div className="animate-pulse rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
      <div className="mb-2 h-4 w-24 rounded bg-[var(--surface-3)]" />
      <div className="h-8 w-16 rounded bg-[var(--surface-3)]" />
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="animate-pulse rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
      <div className="mb-4 h-5 w-32 rounded bg-[var(--surface-3)]" />
      <div className="h-[200px] rounded bg-[var(--surface-3)]" />
    </div>
  );
}

/** Ledger reasons rendered as prose rather than raw enum values. */
const LEDGER_LABELS: Record<string, string> = {
  monthly_grant: 'Monthly allowance',
  signup_bonus: 'Signup bonus',
  purchase: 'Credit purchase',
  admin_adjustment: 'Adjustment',
  refund: 'Refund',
  pipeline_run: 'Pipeline run',
  image_generation: 'Image generation',
  web_search: 'Web search',
};

function DashboardContent() {
  const { quota, loading: quotaLoading } = useQuota();
  const { subscription, loading: subLoading } = useSubscription();
  const { credits, ledger, loading: creditsLoading } = useCredits({ withLedger: true });
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [portalError, setPortalError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    // `historyLoading` already starts `true` (see useState above) and this
    // effect only ever runs once (empty deps), so setting it again here was
    // a redundant synchronous setState — dropped rather than deferred.
    apiFetch('/api/history')
      .then((r) => {
        if (controller.signal.aborted) return null;
        return r.json();
      })
      .then((data) => {
        if (controller.signal.aborted) return;
        setHistory(data?.entries || []);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setHistory([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setHistoryLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  const chartData = history.slice(-7).map((h: HistoryEntry) => ({
    date: h.timestamp?.slice(0, 10) || 'unknown',
    tokens: h.tokens?.total || 0,
  }));

  const openPortal = async () => {
    setPortalError('');
    try {
      const res = await apiFetch('/api/billing/portal', { method: 'POST' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Portal failed (HTTP ${res.status})`);
      }
      const data = await res.json();
      const url = data.portal_url;
      if (!url || typeof url !== 'string' || !isValidPortalUrl(url)) {
        throw new Error('Invalid portal URL');
      }
      window.location.href = url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to open billing portal';
      setPortalError(msg);
    }
  };

  const percent = quota && quota.max > 0 ? Math.min((quota.used / quota.max) * 100, 100) : 0;
  const barColor = percent >= 90 ? 'bg-[var(--red)]' : percent >= 70 ? 'bg-[var(--warn)]' : 'bg-[var(--accent)]';

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-[var(--text)]">Dashboard</h1>

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {creditsLoading ? (
          <StatCardSkeleton />
        ) : (
          <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
            <p className="text-sm text-[var(--text-muted)]">Credits</p>
            <p
              className={`mt-1 text-2xl font-bold ${
                (credits?.balance ?? 0) <= 0 ? 'text-[var(--red)]' : 'text-[var(--text)]'
              }`}
            >
              {credits?.balance?.toLocaleString() ?? '—'}
            </p>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              {credits
                ? `≈ $${credits.balance_usd.toFixed(2)} · ${credits.monthly_allowance.toLocaleString()}/mo`
                : 'Balance unavailable'}
            </p>
            {credits && credits.balance <= 0 && (
              <Link
                href="/pricing"
                className="mt-2 inline-flex text-sm font-medium text-[var(--accent)] hover:underline"
              >
                Top up
              </Link>
            )}
          </div>
        )}

        {quotaLoading ? (
          <StatCardSkeleton />
        ) : (
          <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
            <p className="text-sm text-[var(--text-muted)]">Queries This Month</p>
            <p className="mt-1 text-2xl font-bold text-[var(--text)]">
              {quota?.used ?? 0} / {quota?.max ?? 20}
            </p>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--surface-3)]">
              <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}

        {quotaLoading ? (
          <StatCardSkeleton />
        ) : (
          <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
            <p className="text-sm text-[var(--text-muted)]">Remaining</p>
            <p className="mt-1 text-2xl font-bold text-[var(--text)]">{quota?.remaining ?? '-'}</p>
          </div>
        )}

        {subLoading ? (
          <StatCardSkeleton />
        ) : (
          <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
            <p className="text-sm text-[var(--text-muted)]">Plan</p>
            <p className="mt-1 text-2xl font-bold text-[var(--text)] capitalize">
              {subscription?.tier || 'Free'}
            </p>
            {subscription?.tier && subscription.tier !== 'free' && (
              <button
                onClick={openPortal}
                className="mt-2 flex min-h-[40px] items-center text-sm font-medium text-[var(--accent)] hover:underline"
              >
                Manage Billing
              </button>
            )}
          </div>
        )}
      </div>

      {portalError && (
        <div className="mb-4 rounded-[var(--radius)] bg-[var(--red-bg)] p-3 text-sm text-[var(--red)]" role="alert">
          {portalError}
        </div>
      )}

      {historyLoading ? (
        <ChartSkeleton />
      ) : chartData.length > 0 ? (
        <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="mb-4 font-semibold text-[var(--text)]">Recent Activity</h2>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--surface)',
                    border: '1px solid var(--border)',
                    borderRadius: '0.5rem',
                    color: 'var(--text)',
                  }}
                />
                <Bar dataKey="tokens" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6 text-center text-[var(--text-muted)]">
          No activity yet. Start a conversation to see your usage.
        </div>
      )}

      {ledger.length > 0 && (
        <section className="mt-8 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-[var(--text)]">Credit activity</h2>
            <Link href="/docs/credits" className="text-sm text-[var(--accent)] hover:underline">
              How credits work
            </Link>
          </div>
          <ul className="divide-y divide-[var(--border)]">
            {ledger.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm text-[var(--text)]">
                    {entry.description || LEDGER_LABELS[entry.reason] || entry.reason}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {new Date(entry.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p
                    className={`text-sm font-medium ${
                      entry.delta > 0 ? 'text-[var(--ok)]' : 'text-[var(--text)]'
                    }`}
                  >
                    {entry.delta > 0 ? '+' : ''}
                    {entry.delta.toLocaleString()}
                  </p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {entry.balance_after.toLocaleString()} left
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <div className="mx-auto max-w-5xl px-4 py-8">
        <div className="mb-6 h-8 w-48 animate-pulse rounded bg-[var(--surface-3)]" />
        <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
        <ChartSkeleton />
      </div>
    }>
      <DashboardContent />
    </Suspense>
  );
}
