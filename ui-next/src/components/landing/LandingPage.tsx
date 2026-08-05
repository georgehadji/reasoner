'use client';

import { useAppStore } from '@/stores/app-store';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { BlobBackground } from '@/components/layout/BlobBackground';
import { NeuralConstellation } from '@/components/fx/NeuralConstellation';
import { ArrowRight } from 'lucide-react';

const FEATURES = [
  {
    num: '01',
    title: 'Verified Reasoning',
    desc: 'Every claim is independently scored, cross-checked across models, and labeled with epistemic confidence before you see it. No hallucinations pass through.',
  },
  {
    num: '02',
    title: 'Cross-Lab Consensus',
    desc: 'Runs diverse models from competing labs in parallel. No single vendor bias — independent agents debate and verify every output.',
  },
  {
    num: '03',
    title: 'Grounded Research',
    desc: 'Iterative web search with source verification. Every factual claim is traceable to its origin. No black-box answers.',
  },
  {
    num: '04',
    title: 'Adversarial Critique',
    desc: 'Dedicated critique agents probe for logical flaws, bias, and weak evidence before final synthesis reaches you.',
  },
];

const CAPABILITIES = [
  '17 reasoning methods',
  '90+ AI models',
  '6 model labs',
  '100% verified output',
];

export default function LandingPage() {
  const router = useRouter();

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[var(--bg)] text-[var(--text)]">
      {/* Soft blob background for page body */}
      <BlobBackground />

      <SiteHeader />

      {/* Scroll fade mask — content fades as it reaches the header */}
      <div
        className="pointer-events-none fixed top-0 left-0 right-0 z-40 h-24"
        style={{
          background: 'linear-gradient(to bottom, var(--bg) 0%, transparent 100%)',
        }}
        aria-hidden="true"
      />

      <main id="main-content" className="relative z-10">
        {/* ── Hero ────────────────────────────────────────── */}
        <section className="relative flex min-h-[90vh] flex-col items-center justify-center overflow-hidden px-6 pb-20 pt-28 text-center">
          {/* 3D neural constellation background */}
          <NeuralConstellation className="absolute inset-0 z-0" />

          {/* Vignette overlay for text readability */}
          <div
            className="pointer-events-none absolute inset-0 z-[1]"
            style={{
              background:
                'radial-gradient(ellipse 70% 55% at 50% 45%, transparent 0%, var(--bg) 75%)',
            }}
          />

          {/* Content */}
          <div className="relative z-10">
          <p
            className="animate-fade-up mb-6 text-sm font-medium tracking-widest uppercase text-[var(--text-muted)]"
            style={{ animationDelay: '0ms' }}
          >
            Enterprise-Grade Reasoning
          </p>

          <h1 className="max-w-5xl text-[clamp(3rem,7vw,6rem)] leading-[1.05] tracking-[-0.03em]">
            <motion.span
              className="inline-block font-medium text-[var(--text-muted)] opacity-60"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 0.6, y: 0 }}
              transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.08 }}
            >
              Think with
            </motion.span>
            <motion.span
              className="inline-block font-light text-[var(--text)]"
              initial={{ opacity: 0, y: 28 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.22 }}
              style={{
                marginLeft: '0.3em',
                textShadow: '0 0 40px rgba(224,224,224,0.35), 0 0 100px rgba(160,160,160,0.18)',
              }}
            >
              certainty.
            </motion.span>
          </h1>

          <p
            className="animate-fade-up mt-8 max-w-2xl text-lg leading-relaxed text-[var(--text-muted)]"
            style={{ animationDelay: '160ms' }}
          >
            Reasoner orchestrates multi-agent reasoning pipelines that verify every claim,
            cross-check across independent models, and tell you exactly what to trust.
          </p>

          <div
            className="animate-fade-up mt-12 flex flex-col items-center gap-4 sm:flex-row"
            style={{ animationDelay: '240ms' }}
          >
            <button
              onClick={() => router.push('/chat')}
              className="group flex items-center gap-2.5 rounded-xl bg-[var(--accent)] px-8 py-4 text-base font-semibold text-[var(--accent-text)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-[0.97]"
            >
              Start Reasoning
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" />
            </button>
            <button
              onClick={() => router.push('/about')}
              className="rounded-xl px-8 py-4 text-base font-medium text-[var(--text-2)] transition-colors duration-200 hover:text-[var(--text)]"
            >
              Learn more
            </button>
          </div>

          {/* Capabilities line */}
          <div
            className="animate-fade-up mt-16 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-[var(--text-subtle)]"
            style={{ animationDelay: '320ms' }}
          >
            {CAPABILITIES.map((cap, i) => (
              <span key={cap} className="flex items-center gap-2">
                <span className="h-1 w-1 rounded-full bg-[var(--accent)]" />
                {cap}
              </span>
            ))}
          </div>
          </div>
        </section>

        {/* ── Divider ─────────────────────────────────────── */}
        <div className="mx-auto max-w-4xl px-6">
          <div className="h-px bg-[var(--border)]" />
        </div>

        {/* ── Features ────────────────────────────────────── */}
        <section className="px-6 py-32">
          <div className="mx-auto max-w-5xl">
            <div className="mb-16 grid gap-12 md:grid-cols-2 md:gap-x-16 md:gap-y-20">
              {FEATURES.map(({ num, title, desc }) => (
                <div key={num} className="group">
                  <div className="mb-4 flex items-baseline gap-4">
                    <span className="font-mono text-sm font-medium text-[var(--text-subtle)]">
                      {num}
                    </span>
                    <div className="h-px flex-1 bg-[var(--border)] transition-colors duration-300 group-hover:bg-[var(--border-strong)]" />
                  </div>
                  <h3 className="mb-3 text-2xl font-semibold tracking-tight text-[var(--text)]">
                    {title}
                  </h3>
                  <p className="leading-relaxed text-[var(--text-muted)]">
                    {desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Divider ─────────────────────────────────────── */}
        <div className="mx-auto max-w-4xl px-6">
          <div className="h-px bg-[var(--border)]" />
        </div>

        {/* ── How it works ────────────────────────────────── */}
        <section className="px-6 py-32">
          <div className="mx-auto max-w-5xl">
            <p className="mb-4 text-sm font-medium tracking-widest uppercase text-[var(--accent)]">
              Architecture
            </p>
            <h2 className="mb-20 text-[clamp(2rem,4vw,3rem)] font-semibold tracking-tight text-[var(--text)]">
              How it works
            </h2>

            <div className="space-y-16">
              {[
                {
                  step: '01',
                  title: 'Classify',
                  desc: 'Six sub-agents analyze your problem in parallel — language, complexity, domain, and optimal reasoning method — before any computation begins.',
                },
                {
                  step: '02',
                  title: 'Decompose',
                  desc: 'The problem is broken into structured sub-tasks. Context is vetted against live sources. Nothing proceeds without verified foundations.',
                },
                {
                  step: '03',
                  title: 'Generate & Critique',
                  desc: 'Multiple independent models generate solutions simultaneously. A dedicated critique layer probes each for logical flaws, bias, and weak evidence.',
                },
                {
                  step: '04',
                  title: 'Synthesize & Label',
                  desc: 'The strongest elements are synthesized into a final answer. Every claim is labeled VERIFIED, HYPOTHESIS, or UNKNOWN — so you know exactly what to trust.',
                },
              ].map(({ step, title, desc }) => (
                <div key={step} className="group flex gap-8 md:gap-16">
                  <div className="hidden shrink-0 pt-1 md:block">
                    <span className="font-mono text-5xl font-bold text-[var(--text-subtle)] transition-colors duration-300 group-hover:text-[var(--accent)]">
                      {step}
                    </span>
                  </div>
                  <div className="flex-1">
                    <div className="mb-2 flex items-center gap-4 md:hidden">
                      <span className="font-mono text-2xl font-bold text-[var(--text-subtle)]">
                        {step}
                      </span>
                      <div className="h-px flex-1 bg-[var(--border)]" />
                    </div>
                    <h3 className="mb-3 text-xl font-semibold text-[var(--text)]">
                      {title}
                    </h3>
                    <p className="max-w-xl leading-relaxed text-[var(--text-muted)]">
                      {desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Divider ─────────────────────────────────────── */}
        <div className="mx-auto max-w-4xl px-6">
          <div className="h-px bg-[var(--border)]" />
        </div>

        {/* ── Epistemic labels ────────────────────────────── */}
        <section className="px-6 py-32">
          <div className="mx-auto max-w-4xl">
            <p className="mb-4 text-sm font-medium tracking-widest uppercase text-[var(--accent)]">
              Epistemic Labeling
            </p>
            <h2 className="mb-6 text-[clamp(2rem,4vw,3rem)] font-semibold tracking-tight text-[var(--text)]">
              Know what to trust.
            </h2>
            <p className="mb-16 max-w-xl text-[var(--text-muted)]">
              Every claim in Reasoner&apos;s output carries an epistemic label so you can distinguish facts from inferences at a glance.
            </p>

            <div className="grid gap-6 sm:grid-cols-3">
              {[
                { label: 'VERIFIED', desc: 'Corroborated by multiple independent sources or models.' },
                { label: 'HYPOTHESIS', desc: 'Plausible inference supported by reasoning but not confirmed.' },
                { label: 'UNKNOWN', desc: 'Insufficient evidence — treat with caution.' },
              ].map(({ label, desc }) => (
                <div
                  key={label}
                  className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 transition-all duration-300 hover:border-[var(--border-strong)]"
                >
                  <div className="mb-3 text-sm font-semibold tracking-wider text-[var(--text)]">
                    {label}
                  </div>
                  <p className="text-sm leading-relaxed text-[var(--text-muted)]">
                    {desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Divider ─────────────────────────────────────── */}
        <div className="mx-auto max-w-4xl px-6">
          <div className="h-px bg-[var(--border)]" />
        </div>

        {/* ── Security & Trust (text only) ────────────────── */}
        <section className="px-6 py-32">
          <div className="mx-auto max-w-4xl">
            <p className="mb-4 text-sm font-medium tracking-widest uppercase text-[var(--accent)]">
              Security & Trust
            </p>
            <h2 className="mb-8 text-[clamp(2rem,4vw,3rem)] font-semibold tracking-tight text-[var(--text)]">
              Your data. Your control.
            </h2>
            <div className="grid gap-8 md:grid-cols-2">
              <div>
                <h3 className="mb-2 text-lg font-medium text-[var(--text)]">End-to-End Encryption</h3>
                <p className="text-[var(--text-muted)]">All memory and session data is encrypted at rest and in transit.</p>
              </div>
              <div>
                <h3 className="mb-2 text-lg font-medium text-[var(--text)]">Privacy First</h3>
                <p className="text-[var(--text-muted)]">We do not train on your data. Conversations stay private by default.</p>
              </div>
              <div>
                <h3 className="mb-2 text-lg font-medium text-[var(--text)]">Self-Hostable</h3>
                <p className="text-[var(--text-muted)]">Full Docker stack with your own Postgres and Valkey.</p>
              </div>
              <div>
                <h3 className="mb-2 text-lg font-medium text-[var(--text)]">Open Source</h3>
                <p className="text-[var(--text-muted)]">MIT licensed. Audit the code, fork it, or deploy it yourself.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ── CTA ─────────────────────────────────────────── */}
        <section className="px-6 py-32">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="mb-6 text-[clamp(2.5rem,5vw,4rem)] font-semibold tracking-[-0.02em] text-[var(--text)]">
              Make decisions you can defend.
            </h2>
            <p className="mb-12 text-lg text-[var(--text-muted)]">
              No setup required. Start reasoning with verified, auditable outputs.
            </p>
            <button
              onClick={() => router.push('/chat')}
              className="group inline-flex items-center gap-2.5 rounded-xl bg-[var(--accent)] px-8 py-4 text-lg font-semibold text-[var(--accent-text)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-[0.97]"
            >
              Open Reasoner
              <ArrowRight className="h-5 w-5 transition-transform duration-200 group-hover:translate-x-1" />
            </button>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
