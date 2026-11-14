'use client';

import { useId, useState } from 'react';
import { MARQUEE_LABS } from '@/lib/capabilities.generated';

/**
 * Large marks on tiles: the labs a run can reach, each tile one lab and the
 * country it is based in. The heading tile carries the Western-only switch;
 * turned on, every lab outside the US and EU is marked "not used", which is
 * what the provider builder enforces (core/model_policy.restrict_blocs()).
 *
 * An unmapped lab renders without a country: a missing origin is a gap, a
 * guessed one is a false claim.
 */
const LAB_ORIGIN: Readonly<Record<string, string>> = {
  Anthropic: 'US',
  OpenAI: 'US',
  Google: 'US',
  Mistral: 'France',
  DeepSeek: 'China',
  xAI: 'US',
  Perplexity: 'US',
  Qwen: 'China',
  'Moonshot AI': 'China',
  Meta: 'US',
  'Zhipu AI': 'China',
  MiniMax: 'China',
};
const WESTERN = new Set(['US', 'France']);

export function LabBoard() {
  const [western, setWestern] = useState(false);
  const switchId = useId();
  const used = MARQUEE_LABS.filter((l) => !western || WESTERN.has(LAB_ORIGIN[l] ?? '')).length;

  return (
    <section id="labs" aria-labelledby="labs-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-32)]">
      <ul className="grid list-none grid-cols-2 gap-[var(--site-tile-gap)] lg:grid-cols-4" data-reveal>
        <li className="col-span-2 flex min-h-[var(--space-48)] flex-col justify-between gap-[var(--space-8)] rounded-[var(--site-radius)] bg-[var(--site-accent)] p-[var(--space-6)] text-[var(--site-accent-ink)] lg:row-span-2">
          <h2 id="labs-h" className="font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]">
            You choose which labs see it.
          </h2>
          <div>
            <p className="max-w-[44ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
              By default a run draws on rival labs, so no single one sets the answer. Western-only
              uses US and EU models and refuses any other, even when a model fails.
            </p>
            <label htmlFor={switchId} className="mt-[var(--space-6)] inline-flex cursor-pointer items-center gap-[var(--space-3)] font-semibold">
              <input
                id={switchId}
                type="checkbox"
                role="switch"
                checked={western}
                onChange={(e) => setWestern(e.target.checked)}
                className="peer sr-only"
              />
              <span
                aria-hidden="true"
                className="relative h-[var(--space-6)] w-[var(--space-10)] rounded-[var(--radius-pill)] bg-[var(--site-accent-ink)] transition-colors peer-checked:bg-[var(--site-bg)] peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 after:absolute after:left-[var(--space-1)] after:top-[var(--space-1)] after:h-[var(--space-4)] after:w-[var(--space-4)] after:rounded-[var(--radius-pill)] after:bg-[var(--site-accent)] after:transition-transform after:duration-[var(--dur-state)] peer-checked:after:translate-x-[var(--space-4)]"
              />
              Western-only
            </label>
            <p aria-live="polite" className="mt-[var(--space-2)] text-[length:var(--site-small)]">
              {used} of {MARQUEE_LABS.length} labs in use
            </p>
          </div>
        </li>

        {MARQUEE_LABS.map((lab) => {
          const origin = LAB_ORIGIN[lab];
          const off = western && !WESTERN.has(origin ?? '');
          return (
            <li
              key={lab}
              className={`flex aspect-[3/2] flex-col justify-between rounded-[var(--site-radius)] p-[var(--space-6)] transition-colors duration-[var(--dur-state)] ${
                off ? 'bg-[var(--site-bg)] text-[var(--site-muted)]' : 'bg-[var(--site-surface)] text-[var(--site-ink)]'
              }`}
            >
              <span className={`font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)] ${off ? 'line-through decoration-2' : ''}`}>
                {lab}
              </span>
              <span className="text-[length:var(--site-small)] text-[var(--site-muted)]">
                {origin ?? ''}
                {off ? ' · not used' : ''}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-[var(--space-6)] max-w-[60ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
        Every provider a request can reach is listed in{' '}
        <a href="/subprocessors" className="site-link">
          sub-processors
        </a>
        , generated from the routing registry.
      </p>
    </section>
  );
}
