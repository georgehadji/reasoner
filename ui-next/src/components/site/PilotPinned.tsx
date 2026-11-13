'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Pinned fragment, changing state: how a pilot runs, in three statements.
 * The stage on the right holds one pilot brief; as each statement reaches
 * the middle of the viewport the brief moves to the matching state.
 *
 * The pilot as the owner has defined it: paid, four to six weeks, one named
 * problem, judged against the team's own analysis. The example problem is a
 * sample, not a client. The comparison stays empty because no pilot result
 * is published; it fills in at the end of a real pilot.
 */
const STEPS = [
  {
    title: 'Name one problem.',
    detail: 'A decision your team would otherwise review by hand, the kind where a confident wrong answer costs you.',
  },
  {
    title: 'Then choose who sees it.',
    detail: 'Western-only if you need it, with every lab the run may use listed before it starts.',
  },
  {
    title: 'Judge it against your team.',
    detail: 'Your team analyses the same problem the usual way. Four to six weeks later, the two are compared line by line.',
  },
] as const;

const SAMPLE_PROBLEM = 'Pre-mortem: why would our switch to a second supplier fail within a year?';
const WESTERN_LABS = ['Anthropic', 'OpenAI', 'Google', 'Mistral', 'xAI', 'Perplexity', 'Meta'];

export function PilotPinned() {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setStep(Number((e.target as HTMLElement).dataset.step));
        }
      },
      { rootMargin: '-45% 0px -45% 0px' },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <section id="pilot" aria-labelledby="pilot-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
      <div className="grid gap-[var(--space-10)] lg:grid-cols-12">
        <div className="lg:col-span-5">
          <h2 id="pilot-h" className="font-display text-[length:var(--site-lead)] leading-[var(--site-lh-head)]">
            How a pilot runs
          </h2>
          <ol className="list-none">
            {STEPS.map((s, i) => (
              <li
                key={s.title}
                data-step={i}
                ref={(el) => {
                  refs.current[i] = el;
                }}
                className="flex min-h-[var(--site-statement-h-phone)] flex-col justify-center lg:min-h-[var(--site-statement-h)]"
              >
                <p
                  className={`font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)] transition-colors duration-[var(--dur-state)] ${
                    step === i ? 'text-[var(--site-ink)]' : 'text-[var(--site-muted)]'
                  }`}
                >
                  {s.title}
                </p>
                <p className="mt-[var(--space-4)] max-w-[44ch] text-[length:var(--site-body)] leading-[var(--site-lh-body)]">
                  {s.detail}
                </p>
              </li>
            ))}
          </ol>
        </div>

        {/* order-first on phones: the stage sticks at the top above the
            statements. Desktop: columns 7-12, sticky at 14vh. */}
        <div className="order-first lg:order-none lg:col-span-6 lg:col-start-7">
          <div className="sticky top-[var(--site-sticky-top)] z-10 rounded-[var(--site-radius)] bg-[var(--site-surface)] p-[var(--space-6)] lg:p-[var(--space-10)]">
            <div data-ui aria-live="polite" className="mx-auto w-full max-w-[var(--site-fragment)] rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)]">
              <div className="flex items-center justify-between border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
                <span className="font-semibold">Pilot brief</span>
                <span className="text-[var(--site-muted)]">Step {step + 1} of 3</span>
              </div>

              <div className="space-y-[var(--space-4)] p-[var(--space-4)]">
                <div>
                  <p className="text-[var(--site-muted)]">Problem</p>
                  <p
                    className={`mt-[var(--space-1)] min-h-[var(--space-10)] rounded-[var(--radius)] border px-[var(--space-3)] py-[var(--space-2)] transition-colors duration-[var(--dur-state)] ${
                      step === 0 ? 'border-[var(--site-accent)]' : 'border-[var(--site-line)]'
                    }`}
                  >
                    {SAMPLE_PROBLEM}
                  </p>
                </div>

                <div className={step >= 1 ? '' : 'text-[var(--site-muted)]'}>
                  <p className="text-[var(--site-muted)]">Routing</p>
                  <div className="mt-[var(--space-1)] inline-flex rounded-[var(--radius)] border border-[var(--site-line)] p-[var(--space-1)]">
                    {['All labs', 'Western-only'].map((r, i) => (
                      <span
                        key={r}
                        className={`rounded-[var(--radius-sm)] px-[var(--space-3)] py-[var(--space-1)] transition-colors duration-[var(--dur-state)] ${
                          step >= 1 && i === 1 ? 'bg-[var(--site-accent)] font-semibold text-[var(--site-accent-ink)]' : ''
                        }`}
                      >
                        {r}
                      </span>
                    ))}
                  </div>
                  {step >= 1 && (
                    <p className="mt-[var(--space-2)] [animation:site-fade_var(--dur-component)_var(--ease-entrance)_both]">
                      {WESTERN_LABS.join(', ')}
                    </p>
                  )}
                </div>

                <div className={step >= 2 ? '' : 'opacity-0'} aria-hidden={step < 2}>
                  <p className="text-[var(--site-muted)]">Compared at week 6</p>
                  <table className="mt-[var(--space-1)] w-full border-collapse">
                    <thead>
                      <tr className="text-left text-[var(--site-muted)]">
                        <th scope="col" className="py-[var(--space-1)] font-normal">Found by</th>
                        <th scope="col" className="py-[var(--space-1)] text-right font-normal">Points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {['The run only', 'Your team only', 'Both'].map((r) => (
                        <tr key={r} className="border-t border-[var(--site-line)]">
                          <th scope="row" className="py-[var(--space-2)] text-left font-semibold">{r}</th>
                          <td className="py-[var(--space-2)] text-right text-[var(--site-muted)]">Filled in at the end</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
