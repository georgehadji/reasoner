import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Security',
  description:
    'How Reasoner protects your data, control by control: encryption at rest and in transit, scoped API keys, an audit log, self-hosting, and how to report a vulnerability. Each with its status.',
  alternates: { canonical: absoluteUrl('/security') },
  openGraph: {
    title: 'Security — Reasoner',
    description: 'Every security control, with its status.',
    url: absoluteUrl('/security'),
    type: 'website',
  },
};

export default function SecurityLayout({ children }: { children: React.ReactNode }) {
  return children;
}
