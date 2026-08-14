import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description:
    'What Reasoner collects, how long it is kept, who it is shared with, and how to export or delete everything associated with your account.',
  alternates: { canonical: absoluteUrl('/privacy') },
};

export default function PrivacyLayout({ children }: { children: React.ReactNode }) {
  return children;
}
