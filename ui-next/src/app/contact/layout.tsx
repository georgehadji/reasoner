import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Contact',
  description:
    'Get in touch with the Reasoner team about support, billing, enterprise plans, or security disclosures.',
  alternates: { canonical: absoluteUrl('/contact') },
  openGraph: {
    title: 'Contact — Reasoner',
    description: 'Support, billing, enterprise, and security contacts.',
    url: absoluteUrl('/contact'),
    type: 'website',
  },
};

export default function ContactLayout({ children }: { children: React.ReactNode }) {
  return children;
}
