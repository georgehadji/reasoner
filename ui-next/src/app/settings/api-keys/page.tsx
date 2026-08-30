'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Check, Copy, Key, Plus, Trash2 } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { apiFetch } from '@/lib/api-client';
import { API, TIMING } from '@/lib/config';
import { useAppStore } from '@/stores/app-store';
import { cn } from '@/lib/utils';

interface ApiKeyRecord {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  is_active: boolean;
}

interface KeyLimits {
  max_keys: number;
  max_expiry_days: number;
  assignable_scopes: string[];
  default_scopes: string[];
}

const SCOPE_LABELS: Record<string, string> = {
  read: 'Run pipelines and read results',
  write: 'Modify settings and clear cache',
  'preset:read': 'List presets and models',
  'history:read': 'Read run history',
  'history:delete': 'Delete history entries',
};

const EXPIRY_OPTIONS = [
  { value: '', label: 'Never expires' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: '1 year' },
];

/** Pure network call, no React state — shared by `load` and the mount effect below. */
async function fetchApiKeysData(): Promise<{ keys: ApiKeyRecord[]; limits: KeyLimits | null }> {
  const res = await apiFetch(API.API_KEYS);
  if (!res.ok) throw new Error(`Could not load keys (HTTP ${res.status})`);
  const data = await res.json();
  return {
    keys: Array.isArray(data?.keys) ? data.keys : [],
    limits: data?.limits ?? null,
  };
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function ApiKeysPage() {
  const user = useAppStore((s) => s.user);
  const router = useRouter();

  const [keys, setKeys] = useState<ApiKeyRecord[]>([]);
  const [limits, setLimits] = useState<KeyLimits | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiry, setExpiry] = useState('');
  const [creating, setCreating] = useState(false);

  const [newKey, setNewKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Exposed for manual re-fetching (e.g. after creating/revoking a key).
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { keys, limits } = await fetchApiKeysData();
      setKeys(keys);
      setLimits(limits);
      if (scopes.length === 0 && Array.isArray(limits?.default_scopes)) {
        setScopes(limits.default_scopes);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load keys');
    } finally {
      setLoading(false);
    }
    // `scopes` is only read to seed the initial selection; re-running on every
    // scope toggle would refetch the list on each checkbox click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mount fetch is intentionally self-contained rather than calling `load`:
  // an Effect must not synchronously trigger a setState chain, which is what
  // calling the (also setState-ing) `load` from here would do. See
  // https://react.dev/learn/you-might-not-need-an-effect#fetching-data.
  useEffect(() => {
    if (!user) {
      router.push('/login');
      return;
    }
    let ignore = false;
    async function loadOnMount() {
      setLoading(true);
      setError('');
      try {
        const { keys, limits } = await fetchApiKeysData();
        if (ignore) return;
        setKeys(keys);
        setLimits(limits);
        if (scopes.length === 0 && Array.isArray(limits?.default_scopes)) {
          setScopes(limits.default_scopes);
        }
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : 'Could not load keys');
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadOnMount();
    return () => {
      ignore = true;
    };
    // Same rationale as `load` above for omitting `scopes`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, router]);

  if (!user) return null;

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setCreating(true);
    setError('');
    try {
      const res = await apiFetch(API.API_KEYS, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          scopes,
          expires_in_days: expiry ? Number(expiry) : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`);
      }
      setNewKey(data.key);
      setName('');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (key: ApiKeyRecord) => {
    const confirmed = window.confirm(
      `Revoke "${key.name}"? Any service using it will start failing immediately. This cannot be undone.`,
    );
    if (!confirmed) return;

    setError('');
    try {
      const res = await apiFetch(API.API_KEY_BY_ID(key.id), { method: 'DELETE' });
      if (!res.ok) throw new Error(`Could not revoke key (HTTP ${res.status})`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not revoke key');
    }
  };

  const handleCopy = async () => {
    if (!newKey) return;
    try {
      await navigator.clipboard.writeText(newKey);
      setCopied(true);
      setTimeout(() => setCopied(false), TIMING.copiedFeedbackMs);
    } catch {
      setError('Could not copy to clipboard — select the key and copy it manually.');
    }
  };

  const toggleScope = (scope: string) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  const atLimit = Boolean(limits && keys.length >= limits.max_keys);

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 pt-24">
        <nav className="mb-6 text-sm text-[var(--text-muted)]">
          <Link href="/settings" className="transition-colors hover:text-[var(--text)]">
            Settings
          </Link>
          <span className="mx-2" aria-hidden="true">
            /
          </span>
          <span className="text-[var(--text-2)]">API keys</span>
        </nav>

        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">API keys</h1>
            <p className="mt-2 max-w-xl text-[var(--text-muted)]">
              Authenticate scripts, agents, and backend services. See the{' '}
              <Link href="/docs/api-keys" className="text-[var(--accent)] hover:underline">
                API keys guide
              </Link>{' '}
              for scopes and rotation.
            </p>
          </div>
          <button
            onClick={() => setShowForm((v) => !v)}
            disabled={atLimit}
            className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[var(--accent-text)] transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            New key
          </button>
        </div>

        {atLimit && limits && (
          <p className="mb-6 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4 text-sm text-[var(--text-2)]">
            You have reached the limit of {limits.max_keys} keys. Revoke one to create another.
          </p>
        )}

        {error && (
          <div
            role="alert"
            className="mb-6 flex items-start gap-2 rounded-lg border border-[var(--red-border)] bg-[var(--red-bg)] p-4 text-sm text-[var(--red)]"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {newKey && (
          <section className="mb-8 rounded-xl border border-[var(--accent)]/40 bg-[var(--accent)]/5 p-5">
            <h2 className="flex items-center gap-2 font-semibold">
              <Key className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" />
              Copy your key now
            </h2>
            <p className="mt-1 text-sm text-[var(--text-2)]">
              This is the only time it will be shown. Only its hash is stored, so it cannot be
              recovered.
            </p>
            <div className="mt-4 flex items-center gap-2">
              <code className="flex-1 overflow-x-auto rounded-lg bg-[var(--surface-2)] px-3 py-2.5 font-mono text-[13px] text-[var(--text)]">
                {newKey}
              </code>
              <button
                onClick={handleCopy}
                className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm font-medium transition-colors hover:bg-[var(--surface-2)]"
              >
                {copied ? (
                  <Check className="h-4 w-4 text-[var(--text)]" aria-hidden="true" />
                ) : (
                  <Copy className="h-4 w-4" aria-hidden="true" />
                )}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <button
              onClick={() => setNewKey(null)}
              className="mt-4 text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
            >
              I have stored it — dismiss
            </button>
          </section>
        )}

        {showForm && limits && (
          <form
            onSubmit={handleCreate}
            className="mb-8 space-y-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
          >
            <div>
              <label htmlFor="key-name" className="mb-1.5 block text-sm font-medium">
                Name
              </label>
              <input
                id="key-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={64}
                placeholder="prod-ingest"
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2.5 text-sm focus:border-[var(--accent)] focus:outline-none"
              />
              <p className="mt-1.5 text-xs text-[var(--text-muted)]">
                Name it after where it runs, so a leak is traceable to one place.
              </p>
            </div>

            <fieldset>
              <legend className="mb-2 text-sm font-medium">Scopes</legend>
              <div className="space-y-2">
                {limits.assignable_scopes.map((scope) => (
                  <label key={scope} className="flex cursor-pointer items-start gap-3 text-sm">
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope)}
                      onChange={() => toggleScope(scope)}
                      className="mt-0.5 h-4 w-4 accent-[var(--accent)]"
                    />
                    <span>
                      <code className="font-mono text-[13px] text-[var(--text)]">{scope}</code>
                      <span className="block text-xs text-[var(--text-muted)]">
                        {SCOPE_LABELS[scope] ?? scope}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                Grant the least a key needs. Scopes can never exceed your own permissions.
              </p>
            </fieldset>

            <div>
              <label htmlFor="key-expiry" className="mb-1.5 block text-sm font-medium">
                Expiry
              </label>
              <select
                id="key-expiry"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2.5 text-sm focus:border-[var(--accent)] focus:outline-none"
              >
                {EXPIRY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-3">
              <button
                type="submit"
                disabled={creating || !name.trim() || scopes.length === 0}
                className="inline-flex h-10 items-center rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[var(--accent-text)] transition-colors hover:bg-[var(--accent-hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creating ? 'Creating…' : 'Create key'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="inline-flex h-10 items-center rounded-lg border border-[var(--border)] px-4 text-sm font-medium transition-colors hover:bg-[var(--surface-2)]"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <div className="space-y-3" aria-busy="true">
            {[0, 1].map((i) => (
              <div
                key={i}
                className="h-24 animate-pulse rounded-xl border border-[var(--border)] bg-[var(--surface)]"
              />
            ))}
          </div>
        ) : keys.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-10 text-center">
            <Key className="mx-auto mb-3 h-8 w-8 text-[var(--text-muted)]" aria-hidden="true" />
            <p className="font-medium">No API keys yet</p>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Create one to call Reasoner from your own code.
            </p>
          </div>
        ) : (
          <ul className="space-y-3">
            {keys.map((key) => (
              <li
                key={key.id}
                className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{key.name}</span>
                    {!key.is_active && (
                      <span className="rounded-full bg-[var(--surface-3)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
                        Expired
                      </span>
                    )}
                  </div>
                  <code className="mt-1 block font-mono text-[13px] text-[var(--text-muted)]">
                    {key.key_prefix}…
                  </code>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {key.scopes.map((scope) => (
                      <span
                        key={scope}
                        className="rounded-md bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-2)]"
                      >
                        {scope}
                      </span>
                    ))}
                  </div>
                  <p className="mt-3 text-xs text-[var(--text-muted)]">
                    Created {formatDate(key.created_at)} · Last used{' '}
                    {formatDate(key.last_used_at)}
                    {key.expires_at ? ` · Expires ${formatDate(key.expires_at)}` : ''}
                  </p>
                </div>
                <button
                  onClick={() => handleRevoke(key)}
                  className={cn(
                    'inline-flex h-9 shrink-0 items-center gap-2 rounded-lg border border-[var(--border)] px-3',
                    'text-sm font-medium text-[var(--text-2)] transition-colors',
                    'hover:border-[var(--red-border)] hover:bg-[var(--red-bg)] hover:text-[var(--red)]',
                  )}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
