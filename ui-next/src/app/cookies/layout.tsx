import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Cookie Policy',
  description:
    'Which cookies Reasoner sets, what each one is for, and how to control them.',
  alternates: { canonical: absoluteUrl('/cookies') },
};

export default function CookiesLayout({ children }: { children: React.ReactNode }) {
  return children;
}
