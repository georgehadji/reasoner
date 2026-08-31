import type { Metadata } from 'next';
import CapabilitiesPage from '@/components/landing/CapabilitiesPage';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'Capabilities',
  description:
    'The eight mechanisms behind a Reasoner run: epistemic labelling, cross-bloc routing, image routing, propagation resistance, sycophancy controls, prose standards, agentic research, and the reasoning methods.',
  alternates: { canonical: absoluteUrl('/capabilities') },
  openGraph: {
    title: `Capabilities — ${SITE.name}`,
    description:
      'Eight mechanisms, and what holds each one — which parts are rules in code and which are briefs given to a model.',
    url: absoluteUrl('/capabilities'),
    type: 'website',
  },
};

export default CapabilitiesPage;
