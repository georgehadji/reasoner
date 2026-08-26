import type { Metadata } from 'next';
import { absoluteUrl } from '@/lib/site';

// Metadata lives here rather than in page.tsx so the two stay separable: the
// page has been a client component before and may be again, and a route-segment
// layout carries the title, description, and canonical URL either way.
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
