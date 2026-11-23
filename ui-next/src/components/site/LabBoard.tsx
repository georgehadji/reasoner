'use client';

import { useId, useState } from 'react';
import { MARQUEE_LABS } from '@/lib/capabilities.generated';

/**
 * The labs a run can reach, grouped by the country each is based in. The
 * heading panel carries the Western-only switch; turned on, every group
 * outside the US and EU is marked "not used", which is what the provider
 * builder enforces (core/model_policy.restrict_blocs()). Grouped, not one tile
 * per lab: a tile held a name and a country and was otherwise empty.
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

/** Countries in the order their first lab appears; '' collects unmapped labs. */
const BY_ORIGIN = MARQUEE_LABS.reduce((m, lab) => {
  const origin = LAB_ORIGIN[lab] ?? '';
  return m.set(origin, [...(m.get(origin) ?? []), lab]);
}, new Map<string, string[]>());

export function LabBoard() {
  const [western, setWestern] = useState(false);
  const switchId = useId();
  const used = MARQUEE_LABS.filter((l) => !western || WESTERN.has(LAB_ORIGIN[l] ?? '')).length;

  return (
    <section id="labs" aria-labelledby="labs-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-32)]">
      <div className="grid gap-[var(--site-tile-gap)] lg:grid-cols-2" data-reveal>
        <div className="flex flex-col justify-between gap-[var(--space-8)] rounded-[var(--site-radius)] bg-[var(--site-accent)] p-[var(--space-6)] text-[var(--site-accent-ink)] lg:p-[var(--space-10)]">
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
        </div>

        <dl className="flex flex-col justify-center gap-[var(--space-10)] rounded-[var(--site-radius)] bg-[var(--site-surface)] p-[var(--space-6)] lg:p-[var(--space-10)]">
          {[...BY_ORIGIN].map(([origin, labs]) => {
            const off = western && !WESTERN.has(origin);
            return (
              <div key={origin || 'unmapped'}>
                <dt className="text-[length:var(--site-small)] text-[var(--site-muted)]">
                  {origin || 'Origin not recorded'}
                  {off ? ' · not used' : ''}
                </dt>
                <dd className="mt-[var(--space-2)]">
                  <ul className="flex list-none flex-wrap gap-x-[var(--space-6)] gap-y-[var(--space-2)]">
                    {labs.map((lab) => (
                      <li
                        key={lab}
                        className={`font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)] transition-colors duration-[var(--dur-state)] ${
                          off ? 'text-[var(--site-muted)] line-through decoration-2' : 'text-[var(--site-ink)]'
                        }`}
                      >
                        {lab}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
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
