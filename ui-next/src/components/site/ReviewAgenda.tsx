'use client';

import Link from 'next/link';
import { useId, useState } from 'react';
import { SECTORS } from '@/lib/sectors';
import { StatusBands } from './StatusBands';

/**
 * Sector tabs over a banded review sheet. Each tab is one sector; its bands
 * are the questions that sector's reviewer asks before a pilot can start,
 * each with its status.
 */
export function ReviewAgenda() {
  const [slug, setSlug] = useState(SECTORS[0].slug);
  const sector = SECTORS.find((s) => s.slug === slug) ?? SECTORS[0];
  const base = useId();

  return (
    <section id="sectors" aria-labelledby="sectors-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-32)]">
      <div className="flex flex-col gap-[var(--space-6)] lg:flex-row lg:items-end lg:justify-between">
        <h2 id="sectors-h" className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">
          <span className="block text-[var(--site-muted)]">Six reviewers,</span>
          <span className="block">six first questions.</span>
        </h2>
        <Link href="/contact?topic=pilot" className="site-button w-full lg:w-auto">
          Propose a pilot
        </Link>
      </div>

      <div className="mt-[var(--space-12)] grid gap-[var(--space-6)] lg:grid-cols-[var(--site-tab)_minmax(0,1fr)] lg:gap-[var(--space-10)]">
        <div
          role="tablist"
          aria-label="Sectors"
          aria-orientation="vertical"
          className="flex flex-wrap gap-[var(--space-2)] lg:flex-col lg:flex-nowrap lg:self-start"
          onKeyDown={(e) => {
            const i = SECTORS.findIndex((s) => s.slug === slug);
            const step = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 0;
            if (!step) return;
            e.preventDefault();
            const next = SECTORS[(i + step + SECTORS.length) % SECTORS.length];
            setSlug(next.slug);
            document.getElementById(`${base}-tab-${next.slug}`)?.focus();
          }}
        >
          {SECTORS.map((s) => {
            const on = s.slug === slug;
            return (
              <button
                key={s.slug}
                id={`${base}-tab-${s.slug}`}
                role="tab"
                type="button"
                aria-selected={on}
                aria-controls={`${base}-panel`}
                tabIndex={on ? 0 : -1}
                onClick={() => setSlug(s.slug)}
                className={`min-h-[var(--space-16)] shrink-0 rounded-[var(--site-radius)] px-[var(--space-4)] py-[var(--space-3)] text-left text-[length:var(--site-small)] font-semibold leading-[var(--lh-tight)] transition-colors duration-[var(--dur-micro)] ${
                  on ? 'bg-[var(--site-ink)] text-[var(--site-bg)]' : 'bg-[var(--site-surface)] text-[var(--site-ink)] hover:bg-[var(--site-surface-2)]'
                }`}
              >
                {s.name}
              </button>
            );
          })}
        </div>

        <div id={`${base}-panel`} role="tabpanel" aria-labelledby={`${base}-tab-${slug}`} className="min-w-0">
          <p className="max-w-[48ch] font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)]">{sector.gate}</p>
          <p className="mt-[var(--space-3)] max-w-[64ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
            {sector.use} <strong className="font-semibold">{sector.limit}</strong>
          </p>

          <StatusBands
            key={slug}
            items={sector.review.map(({ question, status, answer }) => ({ title: question, status, detail: answer }))}
            className="mt-[var(--space-8)] [animation:site-fade_var(--dur-component)_var(--ease-entrance)_both]"
          />

          <Link href={`/for/${sector.slug}`} className="site-link mt-[var(--space-6)] inline-block text-[length:var(--site-body)] font-semibold">
            The full review sheet for {sector.name.toLowerCase()}
          </Link>
        </div>
      </div>
    </section>
  );
}
