interface TestimonialEntry {
  quote: string;
  name: string;
  role: string;
  company: string;
}

/**
 * No entries yet. Renders nothing rather than a placeholder — a landing page
 * with no testimonials reliably outperforms one with an invented or generic
 * one, and a fabricated quote is exactly the class of claim removed from
 * this site in 2026-08. Add a real entry here when one exists; the component
 * needs no other changes.
 */
const TESTIMONIALS: readonly TestimonialEntry[] = [] as const;

export function Testimonial() {
  const entry = TESTIMONIALS[0];
  if (!entry) return null;

  return (
    <figure className="mx-auto max-w-[var(--measure)] text-center">
      <blockquote className="prose-measure font-serif text-[length:var(--text-lg)] leading-[var(--lh-body)] text-[var(--text)]">
        &ldquo;{entry.quote}&rdquo;
      </blockquote>
      <figcaption className="mt-[var(--space-4)] font-sans text-[length:var(--text-sm)] text-[var(--text-muted)]">
        {entry.name}, {entry.role} at {entry.company}
      </figcaption>
    </figure>
  );
}
