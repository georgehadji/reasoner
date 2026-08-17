import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { ShieldCheck, Lock, EyeOff, Scale } from 'lucide-react';

export default function PrivacyPage() {
  const lastUpdated = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto max-w-4xl px-6 py-20 flex-1 w-full">
        <header className="mb-12 border-b border-[var(--border)] pb-12">
          <h1 className="text-4xl md:text-5xl font-bold mb-4 tracking-tight">Privacy Policy</h1>
          <p className="text-[var(--text-muted)] text-lg">Last updated: {lastUpdated}</p>
        </header>

        <div className="grid gap-12 lg:grid-cols-[1fr_280px]">
          <div className="space-y-12 text-[var(--text-muted)] leading-relaxed">
            {/* Mission Statement */}
            <section className="bg-[var(--accent)]/5 border border-[var(--accent)]/10 rounded-2xl p-8 mb-12">
              <h2 className="text-[var(--text)] font-bold text-xl mb-4 flex items-center gap-2">
                <ShieldCheck className="h-6 w-6 text-[var(--accent)]" />
                Our Privacy Commitment
              </h2>
              <p>
                At Reasoner, privacy is not a feature—it is our foundation. We believe that your thoughts and critical 
                reasoning processes should remain yours alone. Our architecture is designed to provide enterprise-grade 
                security while ensuring we have zero access to train models on your proprietary data.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">1. Data Sovereignty & Training</h3>
              <p className="mb-4">
                <strong>Zero-Training Guarantee:</strong> We never use your inputs, outputs, or uploaded files to train 
                or fine-tune our internal models or any third-party models.
              </p>
              <p>
                <strong>Ownership:</strong> You retain full ownership and intellectual property rights to all prompts, 
                contexts, and reasoning outputs generated within your account.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">2. Encryption & Security</h3>
              <p className="mb-4">
                <strong>Encryption at Rest:</strong> All sensitive data, including pipeline snapshots, history, and 
                authentication metadata, is encrypted using industry-standard <strong>AES-256-GCM</strong> before storage.
              </p>
              <p>
                <strong>Encryption in Transit:</strong> Every request is protected via <strong>TLS 1.3</strong>. 
                Our internal architecture utilizes a <strong>Zero-Trust</strong> network where all inter-service 
                communication is authenticated and encrypted via an internal PKI.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">3. Information We Collect</h3>
              <ul className="list-disc pl-6 space-y-3">
                <li><strong>Account Information:</strong> Email address and billing details required to manage your subscription.</li>
                <li><strong>Usage Data:</strong> We collect metadata (timestamp, model used, token count) to provide service reliability and billing accuracy.</li>
                <li><strong>Reasoning Content:</strong> We store your reasoning pipelines to enable history and collaboration. A zero-retention mode is on our roadmap but not yet available.</li>
              </ul>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">4. Data Retention & Deletion</h3>
              <p>
                We do not yet publish a fixed retention period. To request export or deletion of your
                data, contact us via the{' '}
                <a href="/contact" className="underline hover:text-[var(--accent)]">
                  Contact page
                </a>
                {' '}and we will act on it. Self-serve deletion is on our roadmap.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">5. Third-Party LLM Providers</h3>
              <p>
                Reasoner routes requests to the model providers listed on our{' '}
                <a href="/subprocessors" className="underline hover:text-[var(--accent)]">
                  Sub-processors
                </a>{' '}
                page. Each provider's own privacy policy, linked from that page, governs how they
                handle API traffic.
              </p>
            </section>
          </div>

          {/* Quick Info Sidebar */}
          <aside className="space-y-6">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 sticky top-24">
              <h4 className="text-sm font-bold uppercase tracking-wider text-[var(--text-subtle)] mb-4">At a Glance</h4>
              <div className="space-y-4">
                <div className="flex items-start gap-3">
                  <EyeOff className="h-5 w-5 text-[var(--accent)] shrink-0" />
                  <div>
                    <p className="text-sm font-bold text-[var(--text)]">No Training</p>
                    <p className="text-xs">Your data is never used for training.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Lock className="h-5 w-5 text-[var(--accent)] shrink-0" />
                  <div>
                    <p className="text-sm font-bold text-[var(--text)]">AES-256-GCM</p>
                    <p className="text-xs">Standardized encryption at rest.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Scale className="h-5 w-5 text-[var(--accent)] shrink-0" />
                  <div>
                    <p className="text-sm font-bold text-[var(--text)]">GDPR</p>
                    <p className="text-xs">EU data subject rights — export and deletion on request.</p>
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
