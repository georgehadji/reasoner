import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

/**
 * Shared chrome for every documentation page. The sidebar is rendered by each
 * page rather than here so it can mark the active entry. Each page clears the
 * header itself, as the other site pages do.
 */
export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <div className="flex-1">{children}</div>
      <SiteFooter />
    </div>
  );
}
