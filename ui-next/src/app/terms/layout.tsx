import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Terms of Service',
  description:
    'The terms governing use of Reasoner, including acceptable use, credit billing, availability, and liability.',
  alternates: { canonical: absoluteUrl('/terms') },
};

export default function TermsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
