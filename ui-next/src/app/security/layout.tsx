import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Security',
  description:
    'How Reasoner protects your data: AES-256-GCM at rest, TLS 1.3 in transit, prompt-injection defence, scoped API keys, retention controls, and vulnerability disclosure.',
  alternates: { canonical: absoluteUrl('/security') },
  openGraph: {
    title: 'Security — Reasoner',
    description: 'Encryption, retention controls, and defence in depth.',
    url: absoluteUrl('/security'),
    type: 'website',
  },
};

export default function SecurityLayout({ children }: { children: React.ReactNode }) {
  return children;
}
