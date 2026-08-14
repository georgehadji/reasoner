import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'API keys',
  description: 'Create, scope, and revoke your Reasoner API keys.',
  // Authenticated surface — nothing here should ever reach an index.
  robots: { index: false, follow: false },
};

export default function ApiKeysLayout({ children }: { children: React.ReactNode }) {
  return children;
}
