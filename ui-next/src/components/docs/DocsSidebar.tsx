import Link from 'next/link';
import { docsBySection } from '@/lib/docs';

/**
 * Documentation navigation. A server component, so every doc URL is a real
 * anchor in the initial HTML and the whole set is discoverable in one crawl.
 */
export function DocsSidebar({ activeSlug }: { activeSlug?: string }) {
  return (
    <nav aria-label="Documentation" className="text-[length:var(--site-small)] leading-[var(--site-lh-body)]">
      <Link href="/docs" className="site-link font-semibold text-current">
        All guides
      </Link>
      <div className="mt-[var(--space-6)] space-y-[var(--space-6)]">
        {docsBySection().map(({ section, pages }) => (
          <div key={section}>
            <p className="font-semibold">{section}</p>
            <ul className="mt-[var(--space-2)] space-y-[var(--space-1)]">
              {pages.map((page) => {
                const isActive = page.slug === activeSlug;
                return (
                  <li key={page.slug}>
                    <Link
                      href={`/docs/${page.slug}`}
                      aria-current={isActive ? 'page' : undefined}
                      className={
                        isActive
                          ? 'block border-l-2 border-[var(--site-accent)] pl-[var(--space-3)]'
                          : 'block border-l-2 border-transparent pl-[var(--space-3)] text-[var(--site-muted)] hover:text-[var(--site-ink)]'
                      }
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
