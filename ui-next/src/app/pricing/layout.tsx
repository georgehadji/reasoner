import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Pricing',
  description:
    'Reasoner pricing: 500 free credits a month, 25,000 on Pro, 250,000 on Enterprise. 1,000 credits equal $1 of model spend, charged only for runs that complete.',
  alternates: { canonical: absoluteUrl('/pricing') },
  openGraph: {
    title: 'Pricing — Reasoner',
    description: 'Credit-metered pricing. Pay for what completes, not for what you submit.',
    url: absoluteUrl('/pricing'),
    type: 'website',
  },
};

export default function PricingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
