'use client';

import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import { REVIEW_STATUS_LABEL, type ReviewStatus } from '@/lib/sectors';
import { StatusBands, type StatusBand } from './StatusBands';

/**
 * /security's hero and controls sheet, which share one filter.
 *
 * Hero (left): the headline. Hero (right, data-ui): the controls summary as
 * the product would show it, a count per status per group, and a filter
 * that narrows the sheet below to one status. Sheet: one block per group,
 * banded rows with a status each.
 *
 * Every `available` row is backed by code (sources in comments); anything
 * not confirmed is `to-confirm` with an [INPUT REQUIRED] note, never a guess.
 */
const SUB = (
  <Link href="/subprocessors" className="site-link">
    sub-processors
  </Link>
);

interface Group {
  id: string;
  name: string;
  rows: StatusBand[];
}

const GROUPS: Group[] = [
  {
    id: 'data',
    name: 'Your data',
    rows: [
      { title: 'Training by us', status: 'available', detail: 'We do not use your data to train or fine-tune models.' },
      {
        title: 'Training by model providers',
        status: 'to-confirm',
        detail: (
          <>
            Each provider has its own terms; see {SUB}. [INPUT REQUIRED: which providers may retain or
            train on API traffic, and does our OpenRouter account enforce a no-training setting?]
          </>
        ),
      },
      { title: 'Ownership', status: 'available', detail: 'You keep full ownership of your inputs, queries and generated output.' },
      {
        // api/routes/gdpr.py (erase_user_data)
        title: 'Export and deletion',
        status: 'available',
        detail: (
          <>
            One call erases a user&rsquo;s stored data; export on request through{' '}
            <Link href="/contact" className="site-link">
              contact
            </Link>
            .
          </>
        ),
      },
    ],
  },
  {
    id: 'encryption',
    name: 'Encryption',
    rows: [
      {
        title: 'At rest',
        status: 'available',
        detail:
          'Run state, problem text and API key metadata are encrypted per field: Fernet (AES-128-CBC with HMAC) by default, AES-256-GCM when enabled. [INPUT REQUIRED: which format production uses]',
      },
      {
        title: 'In transit',
        status: 'available',
        detail:
          'HTTPS with HSTS. Model calls leave over TLS and are decrypted by the router and the provider, so this is not end-to-end encryption.',
      },
      {
        title: 'Key rotation',
        status: 'available',
        detail: 'A new key goes in front of the old ones: existing data stays readable, new data uses the new key.',
      },
    ],
  },
  {
    id: 'access',
    name: 'Identity and access',
    rows: [
      { title: 'Scoped API keys', status: 'available', detail: 'Each API key carries its own permission scopes.' },
      {
        title: 'Audit log',
        status: 'available',
        detail: 'Sign-in and account events are logged with time, IP address and user agent. Individual reads of your data are not logged.',
      },
      { title: 'Single sign-on', status: 'not-available', detail: 'SAML 2.0 and OIDC (Okta, Azure AD, Google Workspace) are planned, not built.' },
      { title: 'Team roles', status: 'not-available', detail: 'Accounts are individual; there are no organisation roles yet.' },
    ],
  },
  {
    id: 'infrastructure',
    name: 'Infrastructure',
    rows: [
      { title: 'SOC 2 Type II', status: 'not-available', detail: 'Not certified. Ask us for the current status.' },
      {
        title: 'Hosting and network controls',
        status: 'to-confirm',
        detail: '[INPUT REQUIRED: hosting provider, region, and network isolation in production]',
      },
    ],
  },
];

const STATUSES: ReviewStatus[] = ['available', 'not-available', 'to-confirm'];
const count = (rows: StatusBand[], s: ReviewStatus) => rows.filter((r) => r.status === s).length;
const ALL_ROWS = GROUPS.flatMap((g) => g.rows);

export function SecuritySheet({ headline, lede }: { headline: ReactNode; lede: ReactNode }) {
  const [filter, setFilter] = useState<ReviewStatus | 'all'>('all');
  const shown = (rows: StatusBand[]) => (filter === 'all' ? rows : rows.filter((r) => r.status === filter));

  return (
    <>
      <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
        <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
          {headline}
          <div className="site-after-headline">{lede}</div>
        </div>

        <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-32)]">
          <figure
            data-ui
            className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
          >
            <div className="flex items-center justify-between border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
              <span className="font-semibold">Controls</span>
              <span className="text-[var(--site-muted)] nums-tabular">{ALL_ROWS.length} in total</span>
            </div>

            <table className="w-full border-collapse nums-tabular">
              <thead className="text-[var(--site-muted)]">
                <tr>
                  <th scope="col" className="px-[var(--space-4)] py-[var(--space-2)] text-left font-normal">
                    Group
                  </th>
                  {STATUSES.map((s) => (
                    <th key={s} scope="col" className="px-[var(--space-2)] py-[var(--space-2)] text-right font-normal">
                      {REVIEW_STATUS_LABEL[s]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {GROUPS.map((g) => (
                  <tr key={g.id} className="border-t border-[var(--site-line)]">
                    <th scope="row" className="px-[var(--space-4)] py-[var(--space-2)] text-left font-semibold">
                      <a href={`#${g.id}`} className="hover:underline">
                        {g.name}
                      </a>
                    </th>
                    {STATUSES.map((s) => (
                      <td
                        key={s}
                        className={`px-[var(--space-2)] py-[var(--space-2)] text-right transition-colors duration-[var(--dur-micro)] ${
                          filter === s ? 'font-semibold text-[var(--site-accent)]' : ''
                        }`}
                      >
                        {count(g.rows, s)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            <figcaption className="border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
              <span className="text-[var(--site-muted)]">Show in the sheet below</span>
              <div
                role="group"
                aria-label="Filter controls by status"
                className="mt-[var(--space-2)] flex flex-wrap rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]"
              >
                {(['all', ...STATUSES] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    aria-pressed={filter === s}
                    onClick={() => setFilter(s)}
                    className="flex-1 rounded-[var(--radius-sm)] px-[var(--space-3)] py-[var(--space-1)] text-[var(--site-muted)] transition-colors duration-[var(--dur-micro)] hover:text-[var(--site-ink)] aria-pressed:bg-[var(--site-accent)] aria-pressed:font-semibold aria-pressed:text-[var(--site-accent-ink)]"
                  >
                    {s === 'all' ? 'All' : REVIEW_STATUS_LABEL[s]}
                  </button>
                ))}
              </div>
            </figcaption>
          </figure>
        </div>
      </header>

      <section
        id="controls"
        aria-labelledby="controls-h"
        className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]"
      >
        <h2 id="controls-h" className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">
          <span className="block text-[var(--site-muted)]">Every control,</span>
          <span className="block">with its status.</span>
        </h2>
        <p aria-live="polite" className="mt-[var(--space-4)] text-[length:var(--site-body)]">
          {filter === 'all'
            ? `Showing all ${ALL_ROWS.length}.`
            : `Showing ${count(ALL_ROWS, filter)} of ${ALL_ROWS.length}: ${REVIEW_STATUS_LABEL[filter].toLowerCase()}.`}
        </p>

        <div className="mt-[var(--space-12)] space-y-[var(--space-16)]">
          {GROUPS.map((g) => {
            const rows = shown(g.rows);
            if (!rows.length) return null;
            return (
              <div key={g.id} id={g.id} className="grid gap-[var(--space-6)] lg:grid-cols-12 lg:gap-[var(--space-10)]">
                <h3 className="font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)] lg:col-span-3">{g.name}</h3>
                <StatusBands items={rows} className="lg:col-span-9" />
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
