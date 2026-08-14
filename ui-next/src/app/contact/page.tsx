'use client';

import { useState } from 'react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { submitContact } from '@/lib/api-client';

const TOPICS = ['Billing Issue', 'Technical Support', 'Feature Request', 'Other'] as const;

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    email: '',
    topic: TOPICS[0] as string,
    message: '',
  });

  const update = (field: keyof typeof form) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  // Previously this discarded the message and showed a success screen promising
  // a reply within 24 hours. Now the success state only appears once the server
  // confirms the message was accepted for delivery.
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSending(true);
    setError(null);
    try {
      await submitContact(form);
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send your message.');
    } finally {
      setSending(false);
    }
  };

  const inputClass =
    'w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] p-3 text-[var(--text)] focus:border-[var(--accent)] focus:outline-none';

  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-4 py-16 flex-1 w-full">
        <h1 className="text-4xl font-bold mb-8">Contact Support</h1>

        {submitted ? (
          <div className="rounded-lg bg-[#808080]/10 p-6 text-center text-[#A0A0A0] border border-[#808080]/20">
            <h2 className="text-xl font-semibold mb-2">Message sent</h2>
            <p>Thanks for reaching out — we&apos;ve got your message and will reply by email.</p>
            <button
              onClick={() => {
                setSubmitted(false);
                setForm({ name: '', email: '', topic: TOPICS[0], message: '' });
              }}
              className="mt-4 text-[var(--accent)] hover:underline"
            >
              Send another message
            </button>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            className="space-y-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-8"
          >
            {error && (
              <div
                role="alert"
                className="rounded-lg border border-[#B03A2E]/40 bg-[#B03A2E]/10 p-4 text-sm text-[#E4796A]"
              >
                {error}
              </div>
            )}
            <div>
              <label htmlFor="name" className="mb-1 block text-sm font-medium text-[var(--text-2)]">
                Name
              </label>
              <input
                id="name"
                type="text"
                required
                maxLength={120}
                value={form.name}
                onChange={update('name')}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-[var(--text-2)]">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={form.email}
                onChange={update('email')}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="topic" className="mb-1 block text-sm font-medium text-[var(--text-2)]">
                Topic
              </label>
              <select id="topic" value={form.topic} onChange={update('topic')} className={inputClass}>
                {TOPICS.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="message" className="mb-1 block text-sm font-medium text-[var(--text-2)]">
                Message
              </label>
              <textarea
                id="message"
                required
                rows={5}
                maxLength={5000}
                value={form.message}
                onChange={update('message')}
                className={`${inputClass} resize-none`}
              ></textarea>
            </div>
            <button
              type="submit"
              disabled={sending}
              className="w-full rounded-lg bg-[var(--accent)] p-3 font-medium text-[var(--accent-text)] hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {sending ? 'Sending…' : 'Send Message'}
            </button>
          </form>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
