'use client';

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { useRouter } from 'next/navigation';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { LiquidField } from '@/components/ui/LiquidField';
import { ArrowRight } from 'lucide-react';
import { CAPABILITIES as GENERATED_CAPABILITIES, PROVIDERS } from '@/lib/capabilities.generated';
import { DemoReplay } from './DemoReplay';

/* ============================================================
   Bento geometry

   The grid reflows with auto-fit/minmax, so column COUNT is a
   function of available width, not of a breakpoint stack. The two
   container-query thresholds below are the exact widths at which
   auto-fit gains its 2nd and 3rd column for BENTO_MIN + --space-6
   gap (2×320+24 = 664, 3×320+48 = 1008). Keeping the span rules on
   the same numbers is what stops a spanning cell from inventing an
   implicit column — the classic auto-fit + col-span overflow bug.

   Container queries, not viewport media queries: the grid answers to
   the space it is actually given, so it stays correct inside any
   future shell width.
   ============================================================ */
// Absolute, not font-relative. The container-query thresholds this is paired
// with (`@min-[664px]`) are absolute px, so a rem minimum only agrees with them
// at a 16px root. At a 24px root the auto-fit produced ONE explicit track and
// `col-span-2` invented a 195px implicit column — the exact overflow this
// pairing exists to prevent. Raising the browser default font size is a normal
// accessibility setting, so both halves must use the same unit.
const BENTO_MIN = '320px';
const BENTO_GRID: CSSProperties = {
  display: 'grid',
  gap: 'var(--space-6)',
  gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${BENTO_MIN}), 1fr))`,
};
/* 2 columns exist at ≥664px, 3 at ≥1008px. Only the 2-column span is
   used here: four cards at 2+1+1+2 fill exactly two whole rows at three
   columns and two whole rows at two, so the grid never ends ragged. */
const SPAN_2 = '@min-[664px]:col-span-2';

const FEATURES = [
  {
    num: '01',
    title: 'Verified Reasoning',
    desc: 'Every claim is independently scored, cross-checked across models, and labeled VERIFIED, HYPOTHESIS, or UNKNOWN before you see it — never presented as fact without that label.',
    featured: true,
    span: SPAN_2,
  },
  {
    num: '02',
    title: 'Cross-Lab Consensus',
    desc: 'Runs diverse models from competing labs in parallel. No single vendor bias — independent agents debate and verify every output.',
    featured: false,
    span: '',
  },
  {
    num: '03',
    title: 'Grounded Research',
    desc: 'Iterative web search with source verification. Every factual claim is traceable to its origin. No black-box answers.',
    featured: false,
    span: '',
  },
  {
    num: '04',
    title: 'Adversarial Critique',
    desc: 'Dedicated critique agents probe for logical flaws, bias, and weak evidence before final synthesis reaches you.',
    featured: false,
    span: SPAN_2,
  },
];

/* Generated from live registry/preset/phase counts by
   scripts/update_mindmap_meta.py — see capabilities.generated.ts. Never
   hand-edit a number here; it drifts from the code the moment you do. */
const CAPABILITIES = [
  `${GENERATED_CAPABILITIES.methods} reasoning methods`,
  `${GENERATED_CAPABILITIES.routableModels}+ AI models`,
  `${GENERATED_CAPABILITIES.providerAdapters} model labs`,
  'Every claim epistemically labeled',
];

/* The `tone` class carries a colour AND a border style (solid / dashed
   / dotted), so the three states stay distinguishable in greyscale and
   under every form of colour blindness. */
const EPISTEMIC = [
  {
    label: 'VERIFIED',
    desc: 'Corroborated by multiple independent sources or models.',
    tone: 'epistemic-verified',
  },
  {
    label: 'HYPOTHESIS',
    desc: 'Plausible inference supported by reasoning but not confirmed.',
    tone: 'epistemic-hypothesis',
  },
  {
    label: 'UNKNOWN',
    desc: 'Insufficient evidence — treat with caution.',
    tone: 'epistemic-unknown',
  },
];

const TRUST = [
  {
    title: 'End-to-End Encryption',
    desc: 'All memory and session data is encrypted at rest and in transit.',
  },
  {
    title: 'Privacy First',
    desc: 'We do not train on your data. Conversations stay private by default.',
  },
  {
    title: 'Self-Hostable',
    desc: 'Full Docker stack with your own Postgres and Valkey.',
  },
  {
    title: 'Source-Available',
    desc: 'Read the code under a Business Source License. Converts to Apache-2.0 in 2030.',
  },
];

/* ============================================================
   Scroll choreography — ONE idea, used everywhere

   A short fade-and-rise as a section crosses into view, children
   offset by --stagger-step. Every section uses it; nothing else on
   the page is scroll-linked, which is what keeps it from reading as
   noise.

   The transition is CSS, so the global prefers-reduced-motion rule
   already collapses its duration. The explicit media-query read below
   goes further and never hides the content in the first place, nor
   holds it behind a stagger delay — a delay is the one part of a
   transition that CSS in another file cannot take back from an inline
   style. The same branch covers a missing IntersectionObserver, so the
   page can never end up permanently blank.
   ============================================================ */

interface RevealState {
  shown: boolean;
  reduced: boolean;
}

const RevealContext = createContext<RevealState>({ shown: true, reduced: false });

/* Single source of truth for the motion preference on this page.
   The CSS in globals.css already collapses every animation and
   transition under `prefers-reduced-motion`, but it cannot reach an
   inline `animation-delay` — so a reduced-motion visitor would still
   wait out the hero's stagger staring at opacity 0. Reading the query
   here lets the delays go to zero as well.

   Both environment reads below go through useSyncExternalStore rather
   than useState + useEffect. That is not a style preference: a browser
   media query IS an external store, and the alternative is a
   synchronous setState inside an effect, which cascades a second render
   on every mount. The server snapshot is the third argument, so
   hydration has something to agree with. */
const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

function subscribeToMotionPreference(onChange: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {};
  }

  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

function readMotionPreference(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia(REDUCED_MOTION_QUERY).matches
  );
}

function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribeToMotionPreference, readMotionPreference, () => false);
}

/* Capability probe, same shape. The server snapshot is `true` —
   "assume supported" — so SSR keeps emitting the pre-reveal opacity and
   hydration matches; a browser that really lacks the API reports false
   on the client and the scroll gate is skipped entirely, which is what
   stops the page from being permanently blank. */
const NEVER_CHANGES = () => () => {};

function useSupportsIntersectionObserver(): boolean {
  return useSyncExternalStore(
    NEVER_CHANGES,
    () => typeof IntersectionObserver !== 'undefined',
    () => true,
  );
}

/* Hero entrance. One helper instead of six hand-written inline objects,
   so the stagger cadence is stated once. */
function heroEntrance(step: number, reduced: boolean): CSSProperties {
  return {
    animationDelay: reduced ? '0ms' : `calc(var(--stagger-step) * ${step})`,
    animationFillMode: 'both',
  };
}

function useSectionReveal<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [intersected, setIntersected] = useState(false);
  const prefersReducedMotion = usePrefersReducedMotion();
  const supportsObserver = useSupportsIntersectionObserver();

  /* Two reasons never to wait for a scroll event: the visitor asked for
     reduced motion, or nothing exists that could ever fire. Both are
     derived, not stored — so the "show it anyway" path costs no render. */
  const skipScrollGate = prefersReducedMotion || !supportsObserver;

  useEffect(() => {
    const node = ref.current;
    if (!node || skipScrollGate) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setIntersected(true);
          observer.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [skipScrollGate]);

  return {
    ref,
    shown: intersected || skipScrollGate,
    reduced: prefersReducedMotion,
  };
}

function revealStyle(shown: boolean, step: number, reduced: boolean): CSSProperties {
  return {
    opacity: shown ? 1 : 0,
    transform: shown ? 'none' : 'translateY(var(--space-4))',
    transition:
      'opacity var(--dur-component) var(--ease-entrance), transform var(--dur-component) var(--ease-entrance)',
    transitionDelay: reduced ? '0ms' : `calc(var(--stagger-step) * ${step})`,
  };
}

function RevealSection({ children, className }: { children: ReactNode; className?: string }) {
  const { ref, shown, reduced } = useSectionReveal<HTMLElement>();

  return (
    <RevealContext.Provider value={{ shown, reduced }}>
      <section ref={ref} className={className}>
        {children}
      </section>
    </RevealContext.Provider>
  );
}

function Reveal({
  step = 0,
  className,
  children,
}: {
  step?: number;
  className?: string;
  children: ReactNode;
}) {
  const { shown, reduced } = useContext(RevealContext);
  return (
    <div data-reveal className={className} style={revealStyle(shown, step, reduced)}>
      {children}
    </div>
  );
}

/* Section eyebrow — the one piece of sans chrome above a serif heading. */
function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="font-sans text-[length:var(--text-sm)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--accent)]">
      {children}
    </p>
  );
}

function Rule() {
  return (
    <div
      className="mx-auto w-full max-w-[var(--width-content)] px-[var(--gutter)]"
      aria-hidden="true"
    >
      <div className="h-px bg-[var(--border)]" />
    </div>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      {/* Scroll fade mask — content fades as it reaches the header */}
      <div
        className="pointer-events-none fixed inset-x-0 top-0 z-40 h-[var(--space-24)]"
        style={{
          background: 'linear-gradient(to bottom, var(--bg) 0%, transparent 100%)',
        }}
        aria-hidden="true"
      />

      {/* The reveal starts at opacity 0 and is lifted by JS. With
          scripting off nothing would ever lift it, so the same markup
          gets a scripting-off escape hatch. `!important` is required:
          the opacity it is overriding is an inline style. */}
      <noscript>
        <style
          dangerouslySetInnerHTML={{
            __html: '[data-reveal]{opacity:1 !important;transform:none !important}',
          }}
        />
      </noscript>

      <main id="main-content" className="relative z-10">
        {/* ── Hero ────────────────────────────────────────────
            The signature: serif display type at --text-6xl against
            sans UI chrome. Entrance is the design system's own
            fade-up keyframe, so the global prefers-reduced-motion rule
            already flattens the animation itself; heroEntrance() drops
            the stagger delay to zero as well, which CSS cannot do to an
            inline style. */}
        <section className="relative flex min-h-[90svh] flex-col items-center justify-center overflow-hidden px-[var(--gutter)] pb-[var(--section-y)] pt-[var(--space-32)] text-center">
          <LiquidField />
          {/* Vignette: pulls the hero's outer edges toward --bg so the display
              type sits on a settled ground rather than a hard flat field. It
              also fades LiquidField's blobs at the edges rather than letting
              them hard-clip against overflow-hidden. */}
          <div
            className="pointer-events-none absolute inset-0 z-[1]"
            style={{
              background:
                'radial-gradient(ellipse 70% 55% at 50% 45%, transparent 0%, var(--bg) 75%)',
            }}
            aria-hidden="true"
          />

          <div className="relative z-10 flex w-full max-w-[var(--width-wide)] flex-col items-center">
            <p
              className="animate-fade-up font-sans text-[length:var(--text-sm)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]"
              style={heroEntrance(0, prefersReducedMotion)}
            >
              Cross-Lab Verified Reasoning
            </p>

            <h1 className="mt-[var(--space-6)] max-w-[var(--width-wide)] font-serif text-[length:var(--text-6xl)] font-normal leading-[var(--lh-display)] tracking-[var(--tracking-tight)]">
              <span
                className="animate-fade-up inline-block text-[var(--text-muted)]"
                style={heroEntrance(1, prefersReducedMotion)}
              >
                Think with
              </span>{' '}
              <span
                className="animate-fade-up-deep hero-heading inline-block text-[var(--text)]"
                style={heroEntrance(3, prefersReducedMotion)}
              >
                certainty.
              </span>
            </h1>

            <p
              className="animate-fade-up prose-measure mt-[var(--space-8)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]"
              style={heroEntrance(4, prefersReducedMotion)}
            >
              Reasoner orchestrates multi-agent reasoning pipelines that verify every claim,
              cross-check across independent models, and tell you exactly what to trust.
            </p>

            <div
              className="animate-fade-up mt-[var(--space-12)] flex flex-col items-center gap-[var(--space-4)] sm:flex-row"
              style={heroEntrance(6, prefersReducedMotion)}
            >
              <button
                onClick={() => router.push('/chat')}
                className="btn-lift group flex min-h-[var(--space-12)] items-center gap-[var(--space-2)] rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] py-[var(--space-4)] font-sans text-[length:var(--text-base)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
              >
                Start Reasoning
                <ArrowRight
                  aria-hidden="true"
                  className="h-[var(--space-4)] w-[var(--space-4)] transition-transform duration-[var(--dur-micro)] ease-[var(--ease-standard)] group-hover:translate-x-[var(--space-1)]"
                />
              </button>
              <button
                onClick={() => router.push('/about')}
                className="link-smooth flex min-h-[var(--space-12)] items-center rounded-[var(--radius)] px-[var(--space-8)] py-[var(--space-4)] font-sans text-[length:var(--text-base)] font-medium leading-[var(--lh-ui)] text-[var(--text-2)] hover:text-[var(--text)]"
              >
                Learn more
              </button>
            </div>

            {/* Capabilities line. `list-style: none` strips list
                semantics in Safari/VoiceOver; the explicit role puts
                them back. */}
            <ul
              role="list"
              className="animate-fade-up nums-tabular mt-[var(--space-16)] flex list-none flex-wrap items-center justify-center gap-x-[var(--space-6)] gap-y-[var(--space-2)] font-sans text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-subtle)]"
              style={heroEntrance(8, prefersReducedMotion)}
            >
              {CAPABILITIES.map((cap) => (
                <li key={cap} className="flex items-center gap-[var(--space-2)]">
                  <span
                    aria-hidden="true"
                    className="h-[var(--space-1)] w-[var(--space-1)] shrink-0 rounded-[var(--radius-pill)] bg-[var(--accent)]"
                  />
                  {cap}
                </li>
              ))}
            </ul>

            {/* Provider strip — "Routes across", never "Trusted by": this is a
                factual routing statement, not a borrowed-endorsement claim. */}
            <div
              className="animate-fade-up mt-[var(--space-10)] flex flex-col items-center gap-[var(--space-3)]"
              style={heroEntrance(9, prefersReducedMotion)}
            >
              <p className="font-sans text-[length:var(--text-xs)] uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-subtle)]">
                Routes across
              </p>
              <ul
                role="list"
                className="flex list-none flex-wrap items-center justify-center gap-x-[var(--space-5)] gap-y-[var(--space-2)]"
              >
                {PROVIDERS.map((name) => (
                  <li
                    key={name}
                    className="font-sans text-[length:var(--text-sm)] font-medium leading-[var(--lh-ui)] text-[var(--text-subtle)]"
                  >
                    {name}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <Rule />

        {/* ── Demo replay ─────────────────────────────────────
            A real captured run, not a mockup — see DemoReplay.tsx header. */}
        <RevealSection className="px-[var(--gutter)] py-[var(--section-y)]">
          <div className="mx-auto mb-[var(--space-12)] w-full max-w-[var(--width-content)] text-center">
            <Reveal>
              <Eyebrow>See It Work</Eyebrow>
              <h2 className="mt-[var(--space-4)] font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Watch a real run.
              </h2>
            </Reveal>
          </div>
          <DemoReplay />
        </RevealSection>

        <Rule />

        {/* ── Features — bento ────────────────────────────────
            Symmetry underneath (one auto-fit track definition),
            asymmetry on top (cell 01 spans two columns and is the
            only filled surface; the rest are quiet outlines). */}
        <RevealSection className="px-[var(--gutter)] py-[var(--section-y)]">
          <div className="@container mx-auto w-full max-w-[var(--width-wide)]" style={BENTO_GRID}>
            {FEATURES.map(({ num, title, desc, featured, span }, i) => (
              <Reveal key={num} step={i} className={span}>
                <article
                  className={`card-hover flex h-full flex-col rounded-[var(--radius-lg)] border p-[var(--space-8)] ${
                    featured
                      ? 'border-[var(--border-strong)] bg-[var(--surface)] shadow-[var(--shadow)]'
                      : 'border-[var(--border)] bg-transparent hover:border-[var(--border-strong)]'
                  }`}
                >
                  <div className="flex items-baseline gap-[var(--space-4)]">
                    <span
                      className={`nums-tabular font-mono text-[length:var(--text-xs)] font-medium leading-[var(--lh-ui)] tracking-[var(--tracking-label)] ${
                        featured ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)]'
                      }`}
                    >
                      {num}
                    </span>
                    <span
                      aria-hidden="true"
                      className={`h-px flex-1 ${
                        featured ? 'bg-[var(--accent-dim)]' : 'bg-[var(--border)]'
                      }`}
                    />
                  </div>

                  <h2
                    className={`mt-[var(--space-4)] font-serif font-semibold text-[var(--text)] ${
                      featured
                        ? 'text-[length:var(--text-3xl)] leading-[var(--lh-heading)] tracking-[var(--tracking-snug)]'
                        : 'text-[length:var(--text-xl)] leading-[var(--lh-subhead)] tracking-[var(--tracking-snug)]'
                    }`}
                  >
                    {title}
                  </h2>

                  <p
                    className={`prose-measure mt-[var(--space-3)] font-serif leading-[var(--lh-body)] text-[var(--text-muted)] ${
                      featured
                        ? 'text-[length:var(--text-md)]'
                        : 'text-[length:var(--text-base)]'
                    }`}
                  >
                    {desc}
                  </p>
                </article>
              </Reveal>
            ))}
          </div>
        </RevealSection>

        <Rule />

        {/* ── For developers ─────────────────────────────────── */}
        <RevealSection className="px-[var(--gutter)] py-[var(--section-y)]">
          <div className="mx-auto grid w-full max-w-[var(--width-wide)] gap-[var(--space-12)] lg:grid-cols-[1fr_1fr] lg:items-start">
            <Reveal>
              <Eyebrow>For Developers</Eyebrow>
              <h2 className="mt-[var(--space-4)] font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Call it from your own code.
              </h2>
              <p className="prose-measure mt-[var(--space-6)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                A typed SDK, a documented HTTP API, and an MCP server so agents can call Reasoner
                as a tool. Scoped, revocable API keys — no dashboard click-through required to
                get started.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap gap-[var(--space-4)]">
                <a
                  href="/docs"
                  className="link-smooth font-sans text-[length:var(--text-sm)] font-semibold text-[var(--accent)] hover:text-[var(--accent-hover)]"
                >
                  Read the docs →
                </a>
              </div>
            </Reveal>

            <Reveal step={1}>
              <pre className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-6)] font-mono text-[length:var(--text-xs)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                <code>{`npm i @reasoner/sdk

curl https://reasoner.app/api/agent/run/sync \\
  -H "Authorization: Bearer $REASONER_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"problem": "..."}'`}</code>
              </pre>
            </Reveal>
          </div>
        </RevealSection>

        <Rule />

        {/* ── Epistemic labels ───────────────────────────────── */}
        <RevealSection className="px-[var(--gutter)] py-[var(--section-y)]">
          <div className="mx-auto w-full max-w-[var(--width-content)]">
            <Reveal>
              <Eyebrow>Epistemic Labeling</Eyebrow>
              <h2 className="mt-[var(--space-4)] font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Know what to trust.
              </h2>
              <p className="prose-measure mt-[var(--space-6)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                Every claim in Reasoner&apos;s output carries an epistemic label so you can
                distinguish facts from inferences at a glance.
              </p>
            </Reveal>

            <div
              className="mt-[var(--space-16)]"
              style={{
                display: 'grid',
                gap: 'var(--space-6)',
                gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 15rem), 1fr))',
              }}
            >
              {EPISTEMIC.map(({ label, desc, tone }, i) => (
                <Reveal key={label} step={i + 1}>
                  <div className="card-hover h-full rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-6)] hover:border-[var(--border-strong)]">
                    <h3
                      className={`${tone} pl-[var(--space-3)] font-sans text-[length:var(--text-sm)] font-semibold uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)]`}
                    >
                      {label}
                    </h3>
                    <p className="mt-[var(--space-4)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                      {desc}
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </RevealSection>

        <Rule />

        {/* ── Security & Trust ───────────────────────────────── */}
        <RevealSection className="px-[var(--gutter)] py-[var(--section-y)]">
          <div className="mx-auto w-full max-w-[var(--width-content)]">
            <Reveal>
              <Eyebrow>Security &amp; Trust</Eyebrow>
              <h2 className="mt-[var(--space-4)] font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Your data. Your control.
              </h2>
            </Reveal>

            <div
              className="mt-[var(--space-16)]"
              style={{
                display: 'grid',
                gap: 'var(--space-8)',
                gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${BENTO_MIN}), 1fr))`,
              }}
            >
              {TRUST.map(({ title, desc }, i) => (
                <Reveal key={title} step={i + 1}>
                  <h3 className="font-serif text-[length:var(--text-lg)] font-semibold leading-[var(--lh-subhead)] tracking-[var(--tracking-snug)] text-[var(--text)]">
                    {title}
                  </h3>
                  <p className="prose-measure mt-[var(--space-2)] font-serif text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                    {desc}
                  </p>
                </Reveal>
              ))}
            </div>
          </div>
        </RevealSection>

        <Rule />

        {/* ── CTA ────────────────────────────────────────────── */}
        <RevealSection className="px-[var(--gutter)] py-[var(--section-y-lg)]">
          <div className="mx-auto w-full max-w-[var(--width-content)] text-center">
            <Reveal>
              <h2 className="mx-auto max-w-[var(--measure-tight)] font-serif text-[length:var(--text-5xl)] font-semibold leading-[var(--lh-display)] tracking-[var(--tracking-tight)] text-[var(--text)]">
                Make decisions you can defend.
              </h2>
            </Reveal>
            <Reveal step={1}>
              <p className="prose-measure mx-auto mt-[var(--space-6)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                No setup required. Start reasoning with verified, auditable outputs.
              </p>
            </Reveal>
            <Reveal step={2}>
              <button
                onClick={() => router.push('/chat')}
                className="btn-lift group mt-[var(--space-12)] inline-flex min-h-[var(--space-12)] items-center gap-[var(--space-2)] rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] py-[var(--space-4)] font-sans text-[length:var(--text-lg)] font-semibold leading-[var(--lh-ui)] text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
              >
                Open Reasoner
                <ArrowRight
                  aria-hidden="true"
                  className="h-[var(--space-5)] w-[var(--space-5)] transition-transform duration-[var(--dur-micro)] ease-[var(--ease-standard)] group-hover:translate-x-[var(--space-1)]"
                />
              </button>
            </Reveal>
          </div>
        </RevealSection>
      </main>

      <SiteFooter />
    </div>
  );
}
