import type { Metadata } from 'next';
import './globals.css';
import { fontVariables } from './fonts';
import { Providers } from './providers';
import { JsonLd } from '@/components/seo/JsonLd';
import { organizationSchema, softwareApplicationSchema, websiteSchema } from '@/lib/schema';
import { SITE, SITE_URL } from '@/lib/site';

export const metadata: Metadata = {
  // Without metadataBase, relative OpenGraph and canonical URLs resolve against
  // localhost in production builds and crawlers see broken absolute links.
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE.name} — ${SITE.tagline}`,
    // Per-page titles get the brand appended automatically, so no page has to
    // remember to do it and none of them can disagree about the format.
    template: `%s — ${SITE.name}`,
  },
  description: SITE.description,
  applicationName: SITE.name,
  keywords: [
    'AI reasoning',
    'multi-model reasoning',
    'AI debate',
    'chain of verification',
    'tree of thoughts',
    'Bayesian reasoning AI',
    'AI research assistant',
    'LLM orchestration',
    'verified AI answers',
  ],
  authors: [{ name: SITE.name, url: SITE_URL }],
  creator: SITE.name,
  publisher: SITE.name,
  alternates: {
    canonical: '/',
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-snippet': -1,
      'max-image-preview': 'large',
      'max-video-preview': -1,
    },
  },
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml', sizes: 'any' },
      { url: '/favicon.ico', sizes: '48x48' },
      { url: '/favicon-32x32.png', type: 'image/png', sizes: '32x32' },
      { url: '/favicon-16x16.png', type: 'image/png', sizes: '16x16' },
    ],
    shortcut: '/favicon.svg',
    apple: '/apple-touch-icon.png',
  },
  openGraph: {
    type: 'website',
    siteName: SITE.name,
    locale: SITE.locale,
    url: SITE_URL,
    title: `${SITE.name} — ${SITE.tagline}`,
    description: SITE.shortDescription,
  },
  twitter: {
    card: 'summary_large_image',
    title: `${SITE.name} — ${SITE.tagline}`,
    description: SITE.shortDescription,
  },
  category: 'technology',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning` is required, not cosmetic: next-themes writes the
    // resolved theme class onto <html> from a blocking inline script before React
    // hydrates, so the server markup and the client DOM intentionally disagree on
    // this one element. Without it React logs a hydration mismatch on every load.
    <html lang="en" className={`${fontVariables} antialiased`} suppressHydrationWarning>
      <body className="min-h-screen bg-[var(--bg)] text-[var(--text)] flex flex-col">
        <JsonLd data={[organizationSchema(), websiteSchema(), softwareApplicationSchema()]} />
        {/* Flyweight gooey filter def — mounted once, referenced by every
            LiquidField via filter: url(#goo). feColorMatrix thresholds alpha
            only (not feColorMatrix on CSS colour), so it composites over
            transparent backgrounds and needs no light/dark branch.
            Invariant: a filter-bearing container must never contain a
            `position: fixed` descendant — fixed elements resolve against the
            nearest filter/backdrop-filter/transform ancestor, not the
            viewport (see SecurityModal's portal-to-body fix). LiquidField is
            leaf decoration for exactly this reason. */}
        <svg
          aria-hidden="true"
          focusable="false"
          style={{ position: 'absolute', width: 0, height: 0 }}
        >
          <defs>
            <filter id="goo" colorInterpolationFilters="sRGB">
              <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur" />
              <feColorMatrix
                in="blur"
                type="matrix"
                values="1 0 0 0 0
                        0 1 0 0 0
                        0 0 1 0 0
                        0 0 0 19 -9"
              />
            </filter>
          </defs>
        </svg>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
