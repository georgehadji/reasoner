import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

// The page itself is a client component and therefore cannot export metadata;
// a route-segment layout is the supported way to give it a title, description,
// and canonical URL without rewriting the page.
export const metadata: Metadata = {
  title: 'About',
  description:
    'Why Reasoner treats reasoning as an engineering problem: structured pipelines, cross-lab model diversity, independent critique, and answers labelled with what is actually known.',
  alternates: { canonical: absoluteUrl('/about') },
  openGraph: {
    title: 'About Reasoner',
    description: 'Reasoning as an engineering problem, not a prompt.',
    url: absoluteUrl('/about'),
    type: 'website',
  },
};

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return children;
}
