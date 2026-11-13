import Link from 'next/link';
import { Lock, Database, Server, Users, ShieldAlert, CheckCircle2, Clock } from 'lucide-react';
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
      {
        done: true,
        label: 'No training by us',
        desc: (
          <>
            We do not use your data to train or fine-tune models. Each model provider has its own
            terms; see{' '}
            <Link href="/subprocessors" className="underline hover:text-[var(--accent)]">
              Sub-processors
            </Link>
            . [INPUT REQUIRED: which providers may retain or train on API traffic, and does our
            OpenRouter account enforce a no-training setting?]
          </>
        ),
      },
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
      {
        done: true,
        label: 'At rest',
        desc: 'Run state, problem text and API key metadata are encrypted at the field level: Fernet (AES-128-CBC with HMAC) by default, AES-256-GCM when enabled. [INPUT REQUIRED: which format production uses]',
      },
      {
        done: true,
        label: 'In transit',
        desc: 'Connections use HTTPS with HSTS. Model calls leave our servers over TLS and are decrypted by the router and the model provider, so this is not end-to-end encryption.',
      },
      {
        done: true,
        label: 'Key rotation',
        desc: 'A new key is added in front of the old ones; existing data stays readable and new data uses the new key.',
      },
    ],
  },
  {
    icon: Server,
    title: 'Infrastructure',
    items: [
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
      {
        done: false,
        label: 'Hosting and network controls',
        desc: '[INPUT REQUIRED: hosting provider, region, and network isolation in production]',
      },
    ],
  },
  {
    icon: Users,
    title: 'Identity & Access',
    items: [
      { done: false, label: 'SSO (SAML 2.0 / OIDC)', desc: 'Okta, Azure AD, and Google Workspace support is planned, not yet available.' },
      { done: true, label: 'Scoped API keys', desc: 'Each API key carries its own permission scopes.' },
      { done: false, label: 'Team roles', desc: 'Not available. Accounts are individual; there are no organisation roles yet.' },
      { done: true, label: 'Audit log', desc: 'Sign-in and account events are logged with time, IP address and user agent. Individual reads of your data are not logged.' },
    ],
  },
];

export default function SecurityPage() {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main className="flex-1">
        {/* ── Masthead ───────────────────────────────────────────
            Left-aligned, not a centred hero with an icon plate, and no
            label above the h1. */}
        <header className="mx-auto w-full max-w-[var(--width-content)] px-[var(--gutter)] pb-[var(--space-16)] pt-[var(--space-48)]">
          <div>
            <div className="min-w-0">
              <h1 className="font-display text-[length:var(--text-4xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)] md:text-[length:var(--text-5xl)]">
                Security &amp; Trust
              </h1>
              <p className="prose-measure mt-[var(--space-6)] text-[length:var(--text-md)] leading-[var(--lh-body)] text-[var(--text-2)]">
                What is in place today, what is not, and what we still have to confirm. A tick means
                it is built; a clock means it is not available or not yet confirmed.

              </p>
            </div>
          </div>
        </header>

        <div className="mx-auto w-full max-w-[var(--width-content)] px-[var(--gutter)] pb-[var(--space-24)]">
        <div className="grid gap-[var(--space-8)] md:grid-cols-2">
          {CARDS.map(({ icon: Icon, title, items }) => (
            <div
              key={title}
              className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)]"
            >
              <Icon className="mb-[var(--space-6)] h-7 w-7 text-[var(--accent)]" aria-hidden="true" />
              <h2 className="font-display text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
                {title}
              </h2>
              <ul className="mt-[var(--space-4)] space-y-[var(--space-4)]">
                {items.map(({ label, desc, done }) => {
                  const StatusIcon = done ? CheckCircle2 : Clock;
                  return (
                    <li key={label} className="flex gap-[var(--space-3)]">
                      <StatusIcon
                        className={`h-5 w-5 shrink-0 ${done ? 'text-[var(--text)]' : 'text-[var(--text-subtle)]'}`}
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
          <h2 className="font-display text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
            Where your data goes
          </h2>
          <p className="prose-measure mt-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            To answer, your request is sent through OpenRouter to one or more of the model providers
            below, each under its own terms. We do not sell your data. Full list, with each
            provider&rsquo;s privacy policy, on{' '}
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
          <h2 className="font-display text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
            Self-hosting
          </h2>
          <p className="prose-measure mt-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-body)] text-[var(--text-muted)]">
            The full stack (API, Postgres, Valkey) runs from one Docker Compose file, so it can run
            inside your own infrastructure; then only the model calls you configure leave your
            network. [INPUT REQUIRED: is self-hosting offered to customers, and on what licence?]
          </p>
        </section>

        <section className="mt-[var(--space-8)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)]">
          <h2 className="font-display text-[length:var(--text-xl)] font-semibold leading-[var(--lh-subhead)] text-[var(--text)]">
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
          <h2 className="font-display text-[length:var(--text-2xl)] font-semibold text-[var(--text)]">
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
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
