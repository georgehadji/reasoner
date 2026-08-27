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
    /* Advertises the machine-readable index from every page. An agent that
       lands anywhere on the site can follow this to /llms.txt rather than
       reconstructing the documentation from rendered navigation — and the
       first thing that file names is the MCP server. A route that sets its
       own `alternates` replaces this object wholesale, so pages that do must
       repeat the entry. */
    types: {
      'text/plain': [
        { url: '/llms.txt', title: `${SITE.name} documentation index for LLMs` },
      ],
    },
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
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
