import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { Gavel, AlertCircle, FileText, Globe } from 'lucide-react';

export default function TermsPage() {
  const lastUpdated = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto max-w-4xl px-6 py-20 flex-1 w-full">
        <header className="mb-12 border-b border-[var(--border)] pb-12">
          <h1 className="text-4xl md:text-5xl font-bold mb-4 tracking-tight">Terms of Service</h1>
          <p className="text-[var(--text-muted)] text-lg">Last updated: {lastUpdated}</p>
        </header>

        <div className="grid gap-12 lg:grid-cols-[1fr_280px]">
          <div className="space-y-12 text-[var(--text-muted)] leading-relaxed">
            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">1. Acceptance of Terms</h3>
              <p>
                By accessing or using the Reasoner platform, you agree to be bound by these Terms of Service 
                and all applicable laws and regulations. If you do not agree with any of these terms, you are 
                prohibited from using or accessing this site.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">2. Use License & Enterprise Rights</h3>
              <p className="mb-4">
                Permission is granted to access and use the Reasoner reasoning engine for professional, 
                educational, or research purposes.
              </p>
              <p>
                <strong>Data Ownership:</strong> Notwithstanding anything to the contrary, the user retains 
                full ownership and intellectual property rights over all inputs and outputs processed 
                through the system. Reasoner claims no ownership over your proprietary reasoning processes.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">3. Service Accuracy & AI Disclaimer</h3>
              <div className="bg-[color-mix(in_oklab,var(--warn)_5%,transparent)] border border-[color-mix(in_oklab,var(--warn)_20%,transparent)] rounded-xl p-6">
                <p className="flex items-center gap-2 font-bold text-[var(--warn)] mb-2">
                  <AlertCircle className="h-5 w-5" />
                  AI Generation Disclosure
                </p>
                <p className="text-sm">
                  Reasoner utilizes advanced artificial intelligence. AI-generated content can contain inaccuracies, 
                  hallucinations, or biases. Our system is designed to provide structured reasoning and verification, 
                  but users must independently verify all critical outputs. Reasoner is a tool for thought, not a 
                  replacement for professional judgment.
                </p>
              </div>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">4. Prohibited Uses</h3>
              <p className="mb-4">You agree not to use the platform to:</p>
              <ul className="list-disc pl-6 space-y-2">
                <li>Generate illegal or harmful content.</li>
                <li>Attempt to reverse-engineer our proprietary reasoning methodologies.</li>
                <li>Exceed assigned rate limits or bypass security controls.</li>
                <li>Use automated systems to &quot;scrape&quot; or extract data without authorization.</li>
              </ul>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">5. Service Availability & Termination</h3>
              <p>
                While we strive for 99.9% uptime, Reasoner is provided &quot;as is&quot;. We reserve the right to
                modify or discontinue the service with reasonable notice to enterprise customers. 
                We may suspend accounts that violate our security policies or terms of use.
              </p>
            </section>

            <section>
              <h3 className="text-2xl font-bold mb-6 text-[var(--text)]">6. Governing Law</h3>
              <p>
                These terms shall be governed by and construed in accordance with the laws of the jurisdiction 
                in which the service provider is headquartered, without regard to its conflict of law provisions.
              </p>
            </section>
          </div>

          {/* Quick Info Sidebar */}
          <aside className="space-y-6">
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 sticky top-24">
              <h4 className="text-sm font-bold uppercase tracking-wider text-[var(--text-subtle)] mb-4">Summary</h4>
              <div className="space-y-4">
                <div className="flex items-start gap-3">
                  <FileText className="h-5 w-5 text-[var(--accent)] shrink-0" />
                  <div>
                    <p className="text-sm font-bold text-[var(--text)]">Professional Use</p>
                    <p className="text-xs">Built for high-stakes reasoning.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Gavel className="h-5 w-5 text-[var(--accent)] shrink-0" />
                  <div>
                    <p className="text-sm font-bold text-[var(--text)]">Your Ownership</p>
                    <p className="text-xs">You own all inputs and outputs.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Globe className="h-5 w-5 text-[var(--accent)] shrink-0" />
                  <div>
                    <p className="text-sm font-bold text-[var(--text)]">Global Compliance</p>
                    <p className="text-xs">Standardized legal frameworks.</p>
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
