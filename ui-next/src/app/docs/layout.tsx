import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

/**
 * Shared chrome for every documentation page. The sidebar is rendered by each
 * page rather than here so it can mark the active entry.
 */
export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <div className="flex-1 pt-16">{children}</div>
      <SiteFooter />
    </div>
  );
}
