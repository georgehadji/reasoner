'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { PILOT_DRAFT_KEY } from '@/lib/pilot-draft';
import { AlertCircle } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { submitContact } from '@/lib/api-client';
import { FAQS, faqAnchor } from '@/lib/faq';
import { securityTxtLines } from '@/lib/security-txt';

/**
 * /contact in the site world "The product performs" (spec/art-direction.md).
 * Hero: the form, and beside it the email it becomes, exactly as
 * src/reasoner/api/routes/contact.py composes it (subject, reply-to, body),
 * updating as the visitor types. Then: answers that may already exist,
 * vulnerability reports, and what happens when a message cannot be sent.
 */

/* `--text-base` (16px) is a floor: iOS Safari zooms on focus below it. */
const FIELD =
  'w-full rounded-[var(--radius)] border border-[var(--site-line)] bg-[var(--site-bg)] input-smooth ' +
  'px-[var(--space-4)] py-[var(--space-3)] ' +
  'text-[length:var(--text-base)] leading-[var(--lh-ui)] text-[var(--site-ink)] ' +
  'placeholder:text-[var(--site-muted)] ' +
  'hover:border-[var(--site-muted)] focus:border-[var(--site-accent)] ' +
  'aria-[invalid=true]:border-[var(--red)] ' +
  'disabled:cursor-not-allowed disabled:opacity-60';

const LABEL = 'mb-[var(--space-2)] block font-semibold';

/* The icon is not decoration: red text alone fails for ~8% of men, and prints
   as grey. */
const FIELD_ERROR = 'mt-[var(--space-2)] flex items-start gap-[var(--space-2)] text-[var(--red)]';

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/* Values are the backend's `Topic` literal (routes/contact.py); only the
   visible labels are sentence case. `?topic=pilot` preselects Pilot. */
const TOPICS = [
  ['Pilot', 'Pilot'],
  ['Billing Issue', 'Billing'],
  ['Technical Support', 'Technical support'],
  ['Feature Request', 'Feature request'],
  ['Other', 'Other'],
] as const;

type FieldName = 'name' | 'email' | 'message';
type FieldErrors = Partial<Record<FieldName, string>>;
interface Draft {
  name: string;
  email: string;
  subject: string;
  message: string;
}

/* Source order, so "first invalid" means the first one the user meets going
   down the page rather than whichever key `validate` happened to set first. */
const FIELD_ORDER: readonly FieldName[] = ['name', 'email', 'message'];

function focusField(form: HTMLFormElement | null, name: FieldName) {
  (form?.elements.namedItem(name) as HTMLElement | null)?.focus();
}

function readDraft(form: HTMLFormElement): Draft {
  const data = new FormData(form);
  return {
    name: String(data.get('name') ?? '').trim(),
    email: String(data.get('email') ?? '').trim(),
    subject: String(data.get('subject') ?? 'Other'),
    message: String(data.get('message') ?? '').trim(),
  };
}

function validate({ name, email, message }: Draft): FieldErrors {
  const errors: FieldErrors = {};
  if (!name) errors.name = 'Enter the name we should reply to.';
  if (!email) errors.email = 'Enter the address we should reply to.';
  else if (!isValidEmail(email)) errors.email = 'Enter an address in the form name@example.com.';
  if (!message) errors.message = 'Tell us what you need help with.';
  return errors;
}

function FieldMessage({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <p id={id} role="alert" className={FIELD_ERROR}>
      <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
      <span>{children}</span>
    </p>
  );
}

/** A value in the email preview, or a muted stand-in until it is typed. */
function Slot({ value, empty }: { value: string; empty: string }) {
  return value ? <>{value}</> : <span className="text-[var(--site-muted)]">{empty}</span>;
}

const BODY = 'text-[length:var(--site-body)] leading-[var(--site-lh-body)]';
const HEAD = 'font-display text-[length:var(--site-head)] leading-[var(--site-lh-head)]';
const CAP = 'border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] font-semibold';
const PRE = 'flex-1 overflow-x-auto whitespace-pre-wrap px-[var(--space-4)] py-[var(--space-4)] font-mono leading-[var(--site-lh-body)]';

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>({ name: '', email: '', subject: 'Billing Issue', message: '' });

  const formRef = useRef<HTMLFormElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const topicRef = useRef<HTMLSelectElement>(null);
  // Both halves of this swap unmount whatever had focus, dropping a keyboard
  // user at <body>. `everSubmitted` is what keeps the return trip from firing
  // on first paint, when `submitted` is false because nothing has happened yet
  // rather than because the user came back.
  const everSubmitted = useRef(false);

  useEffect(() => {
    if (submitted) {
      everSubmitted.current = true;
      successRef.current?.focus();
      return;
    }
    if (everSubmitted.current) focusField(formRef.current, 'name');
  }, [submitted]);

  // Read once on mount rather than via useSearchParams, which would force a
  // Suspense boundary around a page that otherwise renders statically.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get('topic')?.toLowerCase();
    const match = TOPICS.find(([value]) => value.toLowerCase() === wanted);
    if (match && topicRef.current) topicRef.current.value = match[0];

    // The landing page's pilot dialog hands its draft over in sessionStorage,
    // not the URL, so a problem description never lands in a log or history.
    try {
      const stored = sessionStorage.getItem(PILOT_DRAFT_KEY);
      if (stored) {
        sessionStorage.removeItem(PILOT_DRAFT_KEY);
        const field = formRef.current?.elements.namedItem('message');
        if (field instanceof HTMLTextAreaElement && !field.value) field.value = stored;
      }
    } catch {
      /* storage blocked: the form simply starts empty */
    }
    if (formRef.current) setDraft(readDraft(formRef.current));
  }, []);

  const clearError = (field: FieldName) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next: FieldErrors = { ...prev };
      delete next[field];
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (sending) return;
    const form = e.currentTarget;
    const values = readDraft(form);
    const found = validate(values);
    setErrors(found);
    // Focus the first field that failed. `noValidate` turns off the browser's
    // own "go here and fix this", so without this the errors appear below the
    // fold of a long form and focus stays on the submit button.
    const firstInvalid = FIELD_ORDER.find((field) => found[field]);
    if (firstInvalid) {
      focusField(form, firstInvalid);
      return;
    }
    setSendError(null);
    setSending(true);
    try {
      await submitContact(values);
      setSubmitted(true);
    } catch {
      // The fields are uncontrolled and stay mounted, so nothing typed is lost.
      setSendError('Your message was not sent. Check your connection and try again.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      <main id="main-content" className="flex-1">
        {/* ── Hero: statement and the email it becomes (left), the form (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>Tell us what</span>
              </span>
              <span className="site-line">
                <span>you need.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[44ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                A pilot, a bill, a bug or an idea. Your message reaches our team inbox as the email
                below, and the reply comes to the address you give.
              </p>

              <figure
                data-ui
                className="mt-[var(--space-10)] flex min-h-[var(--site-fragment-min-h)] w-full flex-col lg:max-w-[var(--site-fragment)] rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)]"
              >
                <figcaption className={CAP}>The email we receive</figcaption>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-[var(--space-3)] gap-y-[var(--space-1)] border-b border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)]">
                  <dt className="text-[var(--site-muted)]">Subject</dt>
                  <dd className="min-w-0 break-words">
                    [Contact] {draft.subject}: <Slot value={draft.name} empty="your name" />
                  </dd>
                  <dt className="text-[var(--site-muted)]">Reply to</dt>
                  <dd className="min-w-0 break-words">
                    <Slot value={draft.email} empty="your address" />
                  </dd>
                </dl>
                <pre tabIndex={0} className={PRE}>
                  <code>
                    From: <Slot value={draft.name} empty="your name" /> &lt;
                    <Slot value={draft.email} empty="your address" />
                    &gt;{'\n'}Topic: {draft.subject}
                    {'\n\n'}
                    <Slot value={draft.message} empty="Your message." />
                  </code>
                </pre>
              </figure>
            </div>
          </div>

          <div className="flex items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <div className="w-full lg:max-w-[var(--site-dialog)]">
              {submitted ? (
                <div
                  ref={successRef}
                  tabIndex={-1}
                  role="status"
                  className="rounded-[var(--radius-lg)] bg-[var(--site-bg)] p-[var(--space-8)]"
                >
                  <h2 className={HEAD}>Message sent.</h2>
                  <p className={`mt-[var(--space-4)] ${BODY}`}>
                    It is in our inbox. We reply to the address you gave.
                  </p>
                  <button
                    type="button"
                    className="site-button mt-[var(--space-8)]"
                    onClick={() => {
                      setSubmitted(false);
                      setErrors({});
                      setSendError(null);
                    }}
                  >
                    Send another message
                  </button>
                </div>
              ) : (
                <form
                  ref={formRef}
                  onSubmit={handleSubmit}
                  onInput={(e) => setDraft(readDraft(e.currentTarget))}
                  noValidate
                  className="flex flex-col gap-[var(--space-6)]"
                >
                  <div>
                    <label htmlFor="name" className={LABEL}>
                      Name
                    </label>
                    <input
                      id="name"
                      name="name"
                      type="text"
                      autoComplete="name"
                      autoCapitalize="words"
                      required
                      className={FIELD}
                      aria-invalid={!!errors.name}
                      aria-describedby={errors.name ? 'name-error' : undefined}
                      onChange={() => clearError('name')}
                    />
                    {errors.name && <FieldMessage id="name-error">{errors.name}</FieldMessage>}
                  </div>

                  <div>
                    <label htmlFor="email" className={LABEL}>
                      Email
                    </label>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      inputMode="email"
                      autoComplete="email"
                      autoCapitalize="none"
                      spellCheck={false}
                      required
                      className={FIELD}
                      aria-invalid={!!errors.email}
                      aria-describedby={errors.email ? 'email-error' : undefined}
                      onChange={() => clearError('email')}
                    />
                    {errors.email && <FieldMessage id="email-error">{errors.email}</FieldMessage>}
                  </div>

                  <div>
                    <label htmlFor="subject" className={LABEL}>
                      Topic
                    </label>
                    {/* Native select on purpose: the platform's own picker on
                        mobile, keyboard type-ahead, and `color-scheme` paints
                        the option list. */}
                    <select ref={topicRef} id="subject" name="subject" className={FIELD} defaultValue="Billing Issue">
                      {TOPICS.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor="message" className={LABEL}>
                      Message
                    </label>
                    <textarea
                      id="message"
                      name="message"
                      rows={6}
                      required
                      className={`${FIELD} resize-y`}
                      aria-invalid={!!errors.message}
                      aria-describedby={errors.message ? 'message-error' : undefined}
                      onChange={() => clearError('message')}
                    />
                    {errors.message && <FieldMessage id="message-error">{errors.message}</FieldMessage>}
                  </div>

                  {sendError && <FieldMessage id="send-error">{sendError}</FieldMessage>}

                  <button
                    type="submit"
                    className="site-button w-full disabled:opacity-60"
                    disabled={sending}
                    aria-describedby={sendError ? 'send-error' : undefined}
                  >
                    {sending ? 'Sending…' : 'Send message'}
                  </button>
                </form>
              )}
            </div>
          </div>
        </header>

        {/* ── Answers that may already exist ── */}
        <section
          id="answers"
          aria-labelledby="answers-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center"
        >
          <div className="lg:col-span-5">
            <h2 id="answers-h" className={HEAD}>
              <span className="block">It may already</span>
              <span className="block">be answered.</span>
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              Billing, credits, data and the API come up most. Each answer is on one page.
            </p>
          </div>
          <figure
            data-ui
            data-reveal
            className="min-h-[var(--site-fragment-min-h)] w-full min-w-0 rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
          >
            <figcaption className={CAP}>From the FAQ</figcaption>
            <ul className="list-none">
              {FAQS.slice(2, 9).map(({ q }) => (
                <li key={q} className="border-b border-[var(--site-line)] last:border-b-0">
                  <Link href={`/faq#${faqAnchor(q)}`} className="flex justify-between gap-[var(--space-3)] px-[var(--space-4)] py-[var(--space-3)] hover:bg-[var(--site-surface-2)]">
                    <span>{q}</span>
                    <span aria-hidden="true" className="text-[var(--site-muted)]">
                      &rarr;
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </figure>
        </section>

        {/* ── Vulnerabilities: light field, the file left, statement right ── */}
        <section id="security" aria-labelledby="security-h" className="bg-[var(--site-field)] text-[var(--site-field-ink)]">
          <div className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12 lg:items-center">
            <figure
              data-ui
              data-reveal
              className="order-last flex min-h-[var(--site-fragment-min-h)] w-full min-w-0 flex-col rounded-[var(--radius-lg)] bg-[var(--site-bg)] text-[var(--site-ink)] lg:order-none lg:col-span-6"
            >
              <figcaption className={CAP}>
                <a href="/.well-known/security.txt" className="hover:underline">
                  /.well-known/security.txt
                </a>
              </figcaption>
              <pre tabIndex={0} className={PRE}>
                <code>{securityTxtLines().join('\n')}</code>
              </pre>
            </figure>
            <div className="lg:col-span-5 lg:col-start-8">
              <h2 id="security-h" className={HEAD}>
                <span className="block">Found a</span>
                <span className="block">vulnerability?</span>
              </h2>
              <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
                Our security.txt points to this form: choose Technical support and start the message
                with &ldquo;Security&rdquo;. [INPUT REQUIRED: a dedicated security address?] What we have built and what we have not is on{' '}
                <Link href="/security" className="underline underline-offset-4">
                  security
                </Link>
                .
              </p>
            </div>
          </div>
        </section>

        {/* ── Delivery: what the form does when it cannot send ── */}
        <section
          id="delivery"
          aria-labelledby="delivery-h"
          className="mx-auto grid w-full max-w-[var(--site-max)] gap-[var(--space-12)] px-[var(--site-margin)] py-[var(--space-24)] lg:grid-cols-12"
        >
          <div className="lg:col-span-5">
            <h2 id="delivery-h" className={HEAD}>
              <span className="block">If it does not send,</span>
              <span className="block">you will know.</span>
            </h2>
            <p className={`mt-[var(--space-6)] max-w-[44ch] ${BODY}`}>
              The form shows sent only when the email has left. If our inbox is not set up or the mail
              service refuses, it says so and keeps what you wrote, so you can try again.
            </p>
          </div>
          <figure
            data-ui
            data-reveal
            className="flex min-h-[var(--site-fragment-min-h)] w-full min-w-0 flex-col self-end rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-surface)] lg:col-span-6 lg:col-start-7"
          >
            <figcaption className={CAP}>
              <code className="font-mono">POST /api/contact</code>
            </figcaption>
            <pre tabIndex={0} className={PRE}>
              <code>
                {'200  {"status": "sent"}\n\n503  {"detail": "Contact form is not configured"}\n503  {"detail": "Message could not be sent"}'}
              </code>
            </pre>
          </figure>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
