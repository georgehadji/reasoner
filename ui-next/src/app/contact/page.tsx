'use client';

import { useEffect, useRef, useState } from 'react';
import { PILOT_DRAFT_KEY } from '@/lib/pilot-draft';
import { AlertCircle, Check } from 'lucide-react';
import { Button } from '@/components/ui';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { submitContact } from '@/lib/api-client';

/* Field chrome — the same constants the auth screens use. Focus is deliberately
   louder than hover: hover only firms the border, focus firms it AND adds the
   accent ring that `.input-smooth` supplies. A hover state that looks like a
   focus state is the reason keyboard users lose their place.

   `--text-base` (16px) is a floor, not a preference — iOS Safari zooms the
   viewport on focus for anything smaller. */
const FIELD =
  'w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg)] input-smooth ' +
  'px-[var(--space-4)] py-[var(--space-3)] ' +
  'text-[length:var(--text-base)] leading-[var(--lh-ui)] text-[var(--text)] ' +
  'placeholder:text-[var(--text-subtle)] ' +
  'hover:border-[var(--border-strong)] focus:border-[var(--accent)] ' +
  'aria-[invalid=true]:border-[var(--red)] ' +
  'disabled:cursor-not-allowed disabled:opacity-60';

const LABEL =
  'mb-[var(--space-2)] block text-[length:var(--text-sm)] font-medium ' +
  'leading-[var(--lh-ui)] text-[var(--text-2)]';

/* The icon is not decoration: red text alone fails for ~8% of men, and prints
   as grey. */
const FIELD_ERROR =
  'mt-[var(--space-2)] flex items-start gap-[var(--space-2)] ' +
  'text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--red)]';

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/* `?topic=pilot` (the landing page's pilot CTA) preselects the matching option. */
const TOPICS = ['Pilot', 'Billing Issue', 'Technical Support', 'Feature Request', 'Other'] as const;

type FieldName = 'name' | 'email' | 'message';
type FieldErrors = Partial<Record<FieldName, string>>;

/* Source order, so "first invalid" means the first one the user meets going
   down the page rather than whichever key `validate` happened to set first. */
const FIELD_ORDER: readonly FieldName[] = ['name', 'email', 'message'];

function focusField(form: HTMLFormElement | null, name: FieldName) {
  (form?.elements.namedItem(name) as HTMLElement | null)?.focus();
}

/* Fields stay uncontrolled and are read once, on submit, via FormData —
   three useState hooks re-rendering the page on every keystroke buys nothing
   here. onChange only clears an error that is already showing. */
function validate(data: FormData): FieldErrors {
  const errors: FieldErrors = {};
  const name = String(data.get('name') ?? '').trim();
  const email = String(data.get('email') ?? '').trim();
  const message = String(data.get('message') ?? '').trim();

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

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

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
    const match = TOPICS.find((t) => t.toLowerCase() === wanted);
    if (match && topicRef.current) topicRef.current.value = match;

    // The landing page's pilot dialog hands its draft over in sessionStorage,
    // not the URL, so a problem description never lands in a log or history.
    try {
      const draft = sessionStorage.getItem(PILOT_DRAFT_KEY);
      if (!draft) return;
      sessionStorage.removeItem(PILOT_DRAFT_KEY);
      const field = formRef.current?.elements.namedItem('message');
      if (field instanceof HTMLTextAreaElement && !field.value) field.value = draft;
    } catch {
      /* storage blocked: the form simply starts empty */
    }
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
    const data = new FormData(form);
    const found = validate(data);
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
      await submitContact({
        name: String(data.get('name') ?? '').trim(),
        email: String(data.get('email') ?? '').trim(),
        subject: String(data.get('subject') ?? 'Other'),
        message: String(data.get('message') ?? '').trim(),
      });
      setSubmitted(true);
    } catch {
      // The fields are uncontrolled and stay mounted, so nothing typed is lost.
      setSendError('Your message was not sent. Check your connection and try again.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />

      {/* pt clears the fixed header. --section-y is clamp(3rem, 8vw, 8rem), so
          it resolves to 48px on any viewport under 800px while the header bar
          is a fixed 64px — the h1 was overlapped by 16px on a phone. The id is
          the target of the global skip link in layout.tsx. */}
      <main
        id="main-content"
        className="mx-auto w-full max-w-[var(--width-content)] flex-1 px-[var(--gutter)] py-[var(--section-y)] pt-[calc(var(--space-16)+var(--section-y))]"
      >
        <h1 className="font-display mb-[var(--space-8)] text-[length:var(--text-4xl)] font-bold">Contact Support</h1>

        {submitted ? (
          /* Success. Tick + heading + sentence carry the meaning; the tint is
             decoration, so it survives monochrome and colour blindness. */
          <div
            ref={successRef}
            tabIndex={-1}
            role="status"
            className="flex flex-col items-center gap-[var(--space-3)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)] text-center shadow-[var(--shadow)]"
          >
            <Check aria-hidden="true" className="size-[var(--space-8)] text-[var(--text)]" />
            <h2 className="text-[length:var(--text-xl)] font-semibold">Message Sent</h2>
            <p className="max-w-[var(--measure-tight)] text-[length:var(--text-base)] leading-[var(--lh-body)] text-[var(--text-2)]">
              Thank you for reaching out. Our support team will get back to you within 24 hours.
            </p>
            <Button
              type="button"
              variant="secondary"
              size="md"
              className="rounded-[var(--radius)]"
              onClick={() => {
                setSubmitted(false);
                setErrors({});
                setSendError(null);
              }}
            >
              Send another message
            </Button>
          </div>
        ) : (
          <form
            ref={formRef}
            onSubmit={handleSubmit}
            noValidate
            className="flex flex-col gap-[var(--space-6)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)] shadow-[var(--shadow)]"
          >
            <div>
              <label htmlFor="name" className={LABEL}>Name</label>
              <input
                id="name"
                name="name"
                type="text"
                autoComplete="name"
                autoCapitalize="words"
                placeholder="Ada Lovelace"
                required
                className={FIELD}
                aria-invalid={!!errors.name}
                aria-describedby={errors.name ? 'name-error' : undefined}
                onChange={() => clearError('name')}
              />
              {errors.name && <FieldMessage id="name-error">{errors.name}</FieldMessage>}
            </div>

            <div>
              <label htmlFor="email" className={LABEL}>Email</label>
              <input
                id="email"
                name="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="you@example.com"
                required
                className={FIELD}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? 'email-error' : undefined}
                onChange={() => clearError('email')}
              />
              {errors.email && <FieldMessage id="email-error">{errors.email}</FieldMessage>}
            </div>

            <div>
              <label htmlFor="subject" className={LABEL}>Topic</label>
              {/* Native select on purpose: it gets the platform's own picker on
                  mobile, keyboard type-ahead for free, and cannot drift out of
                  sync with the theme — `color-scheme` on :root already tells the
                  browser how to paint the option list in dark mode. */}
              <select ref={topicRef} id="subject" name="subject" className={FIELD} defaultValue="Billing Issue">
                {TOPICS.map((topic) => (
                  <option key={topic}>{topic}</option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="message" className={LABEL}>Message</label>
              <textarea
                id="message"
                name="message"
                rows={5}
                placeholder="What can we help with?"
                required
                className={`${FIELD} resize-y`}
                aria-invalid={!!errors.message}
                aria-describedby={errors.message ? 'message-error' : undefined}
                onChange={() => clearError('message')}
              />
              {errors.message && <FieldMessage id="message-error">{errors.message}</FieldMessage>}
            </div>

            {sendError && <FieldMessage id="send-error">{sendError}</FieldMessage>}

            <Button
              type="submit"
              size="lg"
              className="w-full rounded-[var(--radius)]"
              disabled={sending}
              aria-describedby={sendError ? 'send-error' : undefined}
            >
              {sending ? 'Sending…' : 'Send Message'}
            </Button>
          </form>
        )}
      </main>

      <SiteFooter />
    </div>
  );
}
