'use client';

import { useRouter } from 'next/navigation';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

const CAPABILITIES = [
  {
    title: 'Multi-Method Pipeline',
    desc: 'Instead of one-shot completions, Reasoner breaks down problems using specialized phases: decomposition, RAG vetting, multi-perspective generation, and rigorous synthesis.',
  },
  {
    title: 'Provider Routing',
    desc: 'Seamlessly routes sub-tasks to the best-in-class models from Anthropic, OpenAI, DeepSeek, Google, and more — based on cost, speed, and capability.',
  },
  {
    title: 'Neuro Memory',
    desc: 'A sophisticated caching and embedding engine that learns from past interactions, providing rich context to future queries without overwhelming token limits.',
  },
  {
    title: 'Stress Testing',
    desc: 'Candidate answers are subjected to rigorous critique, factual verification, and logical stress testing before being presented to the user.',
  },
];

export default function AboutPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-24">
        <div className="mb-20 text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-[var(--text)] sm:text-5xl">
            About Reasoner
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-[var(--text-muted)]">
            Advanced Reasoning Architecture. A multi-method AI system designed for complex questions, strategic decisions, and deep research tasks.
          </p>
        </div>

        <div className="grid gap-12 md:grid-cols-2">
          {CAPABILITIES.map(({ title, desc }, i) => (
            <div key={title} className="group">
              <div className="mb-4 flex items-baseline gap-4">
                <span className="font-mono text-sm font-medium text-[var(--text-subtle)]">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div className="h-px flex-1 bg-[var(--border)] transition-colors duration-300 group-hover:bg-[var(--border-strong)]" />
              </div>
              <h3 className="mb-3 text-xl font-semibold text-[var(--text)]">{title}</h3>
              <p className="leading-relaxed text-[var(--text-muted)]">{desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-20 flex justify-center">
          <button
            onClick={() => router.push('/chat')}
            className="rounded-xl bg-[var(--accent)] px-8 py-4 text-base font-semibold text-[var(--accent-text)] transition-all duration-200 hover:bg-[var(--accent-hover)] active:scale-[0.97]"
          >
            Start Reasoning
          </button>
        </div>

        <div className="mt-16 border-t border-[var(--border)] pt-8 text-center text-sm text-[var(--text-subtle)]">
          <p>Reasoner is operated by Georgios-Chrysovalantis Chatzivantsidis.</p>
          <p className="mt-1">
            Questions?{' '}
            <a href="/contact" className="underline hover:text-[var(--accent)]">
              Get in touch
            </a>
            .
          </p>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
