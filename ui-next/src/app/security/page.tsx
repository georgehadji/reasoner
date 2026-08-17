import Link from 'next/link';
import { ShieldCheck, Lock, Database, Server, Users, ShieldAlert, CheckCircle2, Clock } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { PROVIDERS } from '@/lib/capabilities.generated';

interface Item {
  label: string;
  desc: React.ReactNode;
  done: boolean;
}

interface Card {
  icon: typeof Database;
  title: string;
  items: Item[];
}

const CARDS: Card[] = [
  {
    icon: Database,
    title: 'Data Privacy',
    items: [
      { done: true, label: 'No Training', desc: 'Your data is never used to train or fine-tune any model.' },
      { done: true, label: 'Ownership', desc: 'You retain full ownership of your inputs, queries, and generated insights.' },
      {
        done: true,
        label: 'GDPR',
        desc: (
          <>
            EU data subject rights supported — export and deletion on request via{' '}
            <Link href="/contact" className="underline hover:text-[var(--accent)]">
              Contact
            </Link>
            . Sub-processors listed on the{' '}
            <Link href="/subprocessors" className="underline hover:text-[var(--accent)]">
              Sub-processors
            </Link>{' '}
            page.
          </>
        ),
      },
    ],
  },
  {
    icon: Lock,
    title: 'Encryption',
    items: [
      { done: true, label: 'At Rest', desc: 'Stored data is encrypted using AES-256-GCM.' },
      { done: true, label: 'In Transit', desc: 'All connections are protected via TLS 1.3.' },
      { done: true, label: 'Key Management', desc: 'Keys are rotated and isolated per the process documented in our encryption architecture.' },
    ],
  },
  {
    icon: Server,
    title: 'Infrastructure',
    items: [
      { done: true, label: 'Zero-Trust internal network', desc: 'Every internal service call is authenticated and encrypted, independent of the network perimeter.' },
      {
        done: false,
        label: 'SOC 2 Type II',
        desc: (
          <>
            Not yet certified — on the roadmap.{' '}
            <Link href="/contact" className="underline hover:text-[var(--accent)]">
              Ask us
            </Link>{' '}
            for current status.
          </>
        ),
      },
      { done: true, label: 'Network Isolation', desc: 'Runs inside a private network with restricted egress/ingress.' },
    ],
  },
  {
    icon: Users,
    title: 'Identity & Access',
    items: [
      { done: false, label: 'SSO (SAML 2.0 / OIDC)', desc: 'Okta, Azure AD, and Google Workspace support is planned, not yet available.' },
      { done: true, label: 'RBAC', desc: 'Role-based access control for teams and organizations.' },
      { done: true, label: 'Audit Logs', desc: 'Every access is logged.' },
    ],
  },
];

export default function SecurityPage() {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main className="mx-auto w-full max-w-[var(--width-content)] flex-1 px-[var(--gutter)] py-[var(--space-24)]">
        <div className="mb-[var(--space-16)] text-center">
          <div className="mx-auto mb-[var(--space-6)] flex h-16 w-16 items-center justify-center rounded-[var(--radius-lg)] bg-[color-mix(in_oklab,var(--ok)_10%,transparent)] text-[var(--ok)]">
            <ShieldCheck className="h-8 w-8" aria-hidden="true" />
          </div>
          <h1 className="font-serif text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)] md:text-[length:var(--text-5xl)]">
            Security &amp; Trust
          </h1>
          <p className="prose-measure mx-auto mt-[var(--space-6)] font-serif text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            We do not train on your data, we encrypt it end to end, and we log every access.
            Here is exactly what that means today — and what is still on the roadmap.
          </p>
        </div>

        <div className="grid gap-[var(--space-8)] md:grid-cols-2">
          {CARDS.map(({ icon: Icon, title, items }) => (
            <div
              key={title}
              className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)]"
            >
              <Icon className="mb-[var(--space-6)] h-7 w-7 text-[var(--accent)]" aria-hidden="true" />
              <h2 className="font-serif text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
                {title}
              </h2>
              <ul className="mt-[var(--space-4)] space-y-[var(--space-4)]">
                {items.map(({ label, desc, done }) => {
                  const StatusIcon = done ? CheckCircle2 : Clock;
                  return (
                    <li key={label} className="flex gap-[var(--space-3)]">
                      <StatusIcon
                        className={`h-5 w-5 shrink-0 ${done ? 'text-[var(--ok)]' : 'text-[var(--text-subtle)]'}`}
                        aria-hidden="true"
                      />
                      <span className="text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
                        <strong className="text-[var(--text)]">{label}:</strong> {desc}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        <section className="mt-[var(--space-16)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)]">
          <h2 className="font-serif text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
            Where your data goes
          </h2>
          <p className="prose-measure mt-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            Requests are routed to model providers to generate a response. We do not sell your data,
            and no provider we route to trains on API traffic by default. Full list on{' '}
            <Link href="/subprocessors" className="underline hover:text-[var(--accent)]">
              Sub-processors
            </Link>
            .
          </p>
          <ul role="list" className="mt-[var(--space-4)] flex flex-wrap gap-[var(--space-2)]">
            {PROVIDERS.map((name) => (
              <li
                key={name}
                className="rounded-[var(--radius-pill)] border border-[var(--border)] px-[var(--space-3)] py-[var(--space-1)] text-[length:var(--text-xs)] text-[var(--text-muted)]"
              >
                {name}
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-[var(--space-8)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)]">
          <h2 className="font-serif text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
            Self-hosting
          </h2>
          <p className="prose-measure mt-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            If data residency is a hard requirement, run Reasoner in your own infrastructure with your
            own Postgres and Valkey using the published Docker stack. Nothing leaves your network
            except the model calls you configure.
          </p>
        </section>

        <section className="mt-[var(--space-8)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)]">
          <h2 className="font-serif text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
            Report a vulnerability
          </h2>
          <p className="prose-measure mt-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            See{' '}
            <a
              href="/.well-known/security.txt"
              className="underline hover:text-[var(--accent)]"
            >
              /.well-known/security.txt
            </a>{' '}
            (RFC 9116) for a disclosure contact.
          </p>
        </section>

        <section className="mt-[var(--space-16)] rounded-[var(--radius-lg)] border border-[var(--border-strong)] bg-[var(--surface)] p-[var(--space-12)] text-center">
          <ShieldAlert className="mx-auto mb-[var(--space-6)] h-10 w-10 text-[var(--accent)]" aria-hidden="true" />
          <h2 className="font-serif text-[length:var(--text-2xl)] font-semibold text-[var(--text)]">
            Questions?
          </h2>
          <p className="prose-measure mx-auto mt-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            Talk to us about data retention, self-hosting, or our current compliance roadmap.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap justify-center gap-[var(--space-4)]">
            <Link
              href="/contact"
              className="btn-lift rounded-[var(--radius)] bg-[var(--accent)] px-[var(--space-8)] py-[var(--space-4)] font-sans text-[length:var(--text-base)] font-semibold text-[var(--accent-text)] hover:bg-[var(--accent-hover)]"
            >
              Contact Security
            </Link>
            <Link
              href="/docs"
              className="rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] px-[var(--space-8)] py-[var(--space-4)] font-sans text-[length:var(--text-base)] font-semibold text-[var(--text)] hover:bg-[var(--surface-2)]"
            >
              View Docs
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
