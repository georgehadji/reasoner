import Link from 'next/link';
import type { CreditBalance, CreditLedgerEntry } from '@/hooks/useCredits';
import type { QuotaStatus } from '@/hooks/useQuota';
import type { LoadStatus } from '@/hooks/useAsyncAction';
import { RUN_COSTS, runsPerMonth } from '@/lib/credits';

/**
 * The account dashboard, presentation only (the page owns the data).
 *
 * Its one question: how many credits are left, and what will they buy?
 * So the balance is the largest figure, read in runs beside it, and the
 * finding under the title says the same in one line. App style
 * "true-black-flat" in the site palette: depth by lightness alone
 * (--site-bg, --site-surface, --site-surface-2), no card borders, the
 * accent only on data (the quota bar), the primary action an ink pill.
 */

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

const BUDGET = RUN_COSTS.find((r) => r.kind === 'Budget pipeline')!;

const CARD = 'min-w-0 rounded-[var(--radius-lg)] bg-[var(--site-surface)] p-[var(--space-6)]';
const LABEL = 'text-[var(--site-muted)]';
const PRIMARY =
  'inline-flex min-h-[var(--space-10)] items-center justify-center rounded-full bg-[var(--site-ink)] px-[var(--space-5)] font-semibold text-[var(--site-bg)] transition-transform duration-[var(--dur-micro)] active:scale-[0.97]';
const SECONDARY = 'site-link font-semibold text-current';

const fmt = (n: number) => n.toLocaleString('en-US');
/** A sign on every change; U+2212 so the minus is as wide as the plus. */
const signed = (n: number) => (n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : '0');
const when = (iso: string) =>
  new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

function Bone({ className }: { className: string }) {
  return <span aria-hidden className={`block rounded-[var(--radius-sm)] bg-[var(--site-surface-2)] motion-safe:animate-pulse ${className}`} />;
}

export interface DashboardViewProps {
  credits: CreditBalance | null;
  ledger: CreditLedgerEntry[];
  creditsStatus: LoadStatus;
  onRetryCredits: () => void;
  quota: QuotaStatus | null;
  quotaStatus: LoadStatus;
  /** The plan tier; null while it loads or when it could not be read. */
  tier: string | null;
  planLoading: boolean;
  onManageBilling: () => void;
  portalError: string;
}

export function DashboardView({
  credits,
  ledger,
  creditsStatus,
  onRetryCredits,
  quota,
  quotaStatus,
  tier,
  planLoading,
  onManageBilling,
  portalError,
}: DashboardViewProps) {
  const balance = credits?.balance ?? null;
  const empty = balance !== null && balance <= 0;
  const paid = !!tier && tier !== 'free';

  const unlimited = !!quota && (quota.unlimited || quota.max == null);
  const quotaPct = quota && !unlimited && quota.max! > 0 ? Math.min((quota.used / quota.max!) * 100, 100) : 0;

  return (
    <div className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] pb-[var(--space-16)] pt-[var(--space-24)] text-[length:var(--site-small)] leading-[var(--lh-ui)]">
      {/* Title row: the screen, the finding that answers its question, the one primary action. */}
      <div className="flex flex-wrap items-end justify-between gap-[var(--space-6)]">
        <div className="min-w-0">
          <h1 className="font-display text-[length:var(--text-2xl)] leading-[var(--site-lh-head)]">Dashboard</h1>
          <p aria-live="polite" className="mt-[var(--space-3)] text-[length:var(--site-body)]">
            {creditsStatus === 'loading' ? (
              <Bone className="h-[1lh] w-[24ch]" />
            ) : creditsStatus === 'error' ? (
              <>
                Your balance could not be loaded.{' '}
                <button type="button" onClick={onRetryCredits} className={SECONDARY}>
                  Try again
                </button>
              </>
            ) : empty ? (
              <>
                No credits left.{' '}
                <Link href="/pricing" className={SECONDARY}>
                  Top up
                </Link>{' '}
                to run again.
              </>
            ) : (
              `${fmt(balance!)} credits left: ${runsPerMonth(balance!, BUDGET.cost)} budget runs.`
            )}
          </p>
        </div>
        <Link href="/chat" className={PRIMARY}>
          Start a run
        </Link>
      </div>

      {portalError && (
        <p role="alert" className="mt-[var(--space-6)] rounded-[var(--radius)] bg-[var(--red-bg)] p-[var(--space-3)] text-[var(--red)]">
          {portalError}
        </p>
      )}

      <div className="mt-[var(--space-10)] grid gap-[var(--space-4)] lg:grid-cols-3">
        {/* The balance, then the same balance read as runs. */}
        <section aria-labelledby="balance-h" className={`${CARD} lg:col-span-2`}>
          <h2 id="balance-h" className={LABEL}>
            Balance
          </h2>
          {creditsStatus === 'loading' ? (
            <Bone className="mt-[var(--space-2)] h-[var(--space-16)] w-[10ch]" />
          ) : (
            <p className="mt-[var(--space-1)] font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)] nums-tabular">
              {balance === null ? '—' : fmt(balance)}
              <span hidden={balance === null} className="ml-[var(--space-2)] text-[length:var(--site-lead)] text-[var(--site-muted)]">credits</span>
            </p>
          )}
          <p className={`mt-[var(--space-2)] ${LABEL} nums-tabular`}>
            {credits
              ? `About $${credits.balance_usd.toFixed(2)} · ${fmt(credits.monthly_allowance)} a month on your plan`
              : '—'}
          </p>

          <div className="mt-[var(--space-6)] rounded-[var(--radius)] bg-[var(--site-surface-2)] p-[var(--space-4)]">
            <h3 className="font-semibold">What it buys</h3>
            <ul className="mt-[var(--space-2)] list-none">
              {RUN_COSTS.map((r) => (
                <li
                  key={r.kind}
                  className="flex items-baseline justify-between gap-[var(--space-3)] border-t border-[var(--site-line)] py-[var(--space-2)] first:border-t-0"
                >
                  <span>{r.kind}</span>
                  <span className="shrink-0 text-right nums-tabular">
                    {balance === null ? '—' : empty ? '0' : runsPerMonth(balance, r.cost)}
                  </span>
                </li>
              ))}
            </ul>
            <p className={`mt-[var(--space-2)] ${LABEL}`}>
              Typical costs; a run settles at what its models actually cost.{' '}
              <Link href="/docs/credits" className={SECONDARY}>
                How credits work
              </Link>
            </p>
          </div>
        </section>

        {/* The plan and this month's queries. */}
        {/* Three groups spread down the card, so it ends with the balance card and holds no blank band. */}
        <section aria-labelledby="plan-h" className={`${CARD} flex flex-col justify-between gap-[var(--space-6)]`}>
          <div>
          <h2 id="plan-h" className={LABEL}>
            Plan
          </h2>
          {planLoading ? (
            <Bone className="mt-[var(--space-2)] h-[var(--space-8)] w-[8ch]" />
          ) : (
            <p className="mt-[var(--space-1)] text-[length:var(--text-2xl)] capitalize">{tier ?? 'Free'}</p>
          )}
          {paid && (
            <button type="button" onClick={onManageBilling} className={`mt-[var(--space-2)] ${SECONDARY}`}>
              Manage billing
            </button>
          )}
          </div>

          <div>
          <h3 className={LABEL}>Queries this month</h3>
          {quotaStatus === 'loading' ? (
            <Bone className="mt-[var(--space-2)] h-[var(--space-8)] w-[8ch]" />
          ) : !quota ? (
            <p className="mt-[var(--space-1)] text-[length:var(--text-2xl)]">—</p>
          ) : unlimited ? (
            <p className="mt-[var(--space-1)] text-[length:var(--text-2xl)]">{fmt(quota.used)} · no limit</p>
          ) : (
            <>
              <p className="mt-[var(--space-1)] text-[length:var(--text-2xl)] nums-tabular">
                {fmt(quota.used)}
                <span className="text-[length:var(--site-body)] text-[var(--site-muted)]"> of {fmt(quota.max!)}</span>
              </p>
              <div
                role="meter"
                aria-label="Queries used this month"
                aria-valuemin={0}
                aria-valuemax={quota.max!}
                aria-valuenow={quota.used}
                className="mt-[var(--space-3)] h-[var(--space-2)] overflow-hidden rounded-full bg-[var(--site-surface-2)]"
              >
                <div className="h-full rounded-full bg-[var(--site-accent)]" style={{ width: `${quotaPct}%` }} />
              </div>
              <p className={`mt-[var(--space-2)] ${LABEL} nums-tabular`}>
                {fmt(Math.max(quota.max! - quota.used, 0))} left · resets{' '}
                <time dateTime={quota.reset_date}>
                  {new Date(quota.reset_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })}
                </time>
              </p>
            </>
          )}
          </div>

          <div>
          <h3 className={`mb-[var(--space-1)] ${LABEL}`}>Since you joined</h3>
          <dl className="nums-tabular">
            {[
              ['Granted', credits?.lifetime_granted],
              ['Spent', credits?.lifetime_spent],
            ].map(([k, v]) => (
              <div key={k as string} className="flex items-baseline justify-between gap-[var(--space-3)] border-t border-[var(--site-line)] py-[var(--space-2)]">
                <dt>{k}</dt>
                <dd>{typeof v === 'number' ? `${fmt(v)} credits` : '—'}</dd>
              </div>
            ))}
          </dl>
          </div>
        </section>

        {/* What changed the balance, newest first. */}
        <section aria-labelledby="activity-h" className={`${CARD} lg:col-span-3`}>
          <h2 id="activity-h" className="font-semibold">
            Credit activity
          </h2>
          {creditsStatus === 'loading' ? (
            <div className="mt-[var(--space-4)] space-y-[var(--space-3)]">
              <Bone className="h-[var(--space-6)] w-full" />
              <Bone className="h-[var(--space-6)] w-full" />
              <Bone className="h-[var(--space-6)] w-full" />
            </div>
          ) : ledger.length === 0 ? (
            <p className={`mt-[var(--space-3)] ${LABEL}`}>
              {creditsStatus === 'error' ? '—' : 'No credit activity yet. Each run you start appears here with its cost.'}
            </p>
          ) : (
            <ul className="mt-[var(--space-3)] list-none">
              {ledger.map((e) => (
                <li
                  key={e.id}
                  className="flex items-start justify-between gap-[var(--space-4)] border-t border-[var(--site-line)] py-[var(--space-3)] first:border-t-0"
                >
                  <div className="min-w-0">
                    <p className="break-words">{e.description || LEDGER_LABELS[e.reason] || e.reason}</p>
                    <p className={LABEL}>
                      <time dateTime={e.created_at}>{when(e.created_at)}</time>
                    </p>
                  </div>
                  <div className="shrink-0 text-right nums-tabular">
                    <p className={e.delta > 0 ? 'font-semibold' : undefined}>{signed(e.delta)}</p>
                    <p className={LABEL}>{fmt(e.balance_after)} after</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
