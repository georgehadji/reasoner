import Link from 'next/link';
import { docsBySection } from '@/lib/docs';

/**
 * Documentation navigation. A server component, so every doc URL is a real
 * anchor in the initial HTML and the whole set is discoverable in one crawl.
 */
export function DocsSidebar({ activeSlug }: { activeSlug?: string }) {
  return (
    <nav aria-label="Documentation" className="text-[length:var(--text-sm)]">
      <Link
        href="/docs"
        className="mb-6 block text-[length:var(--text-xs)] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)] transition-colors hover:text-[var(--text)]"
      >
        Documentation
      </Link>
      <div className="space-y-7">
        {docsBySection().map(({ section, pages }) => (
          <div key={section}>
            <p className="mb-2 text-[length:var(--text-2xs)] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {section}
            </p>
            <ul className="space-y-0.5">
              {pages.map((page) => {
                const isActive = page.slug === activeSlug;
                return (
                  <li key={page.slug}>
                    <Link
                      href={`/docs/${page.slug}`}
                      aria-current={isActive ? 'page' : undefined}
                      className={[
                        'block rounded-md px-3 py-1.5 -ml-3 transition-colors',
                        isActive
                          ? 'bg-[var(--surface-2)] font-medium text-[var(--text)]'
                          : 'text-[var(--text-muted)] hover:text-[var(--text)]',
                      ].join(' ')}
                    >
                      {page.title}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}
