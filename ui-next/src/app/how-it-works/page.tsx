import type { Metadata } from 'next';
import RunRecord from '@/components/run-record/RunRecord';
import { SITE, absoluteUrl } from '@/lib/site';

export const metadata: Metadata = {
  title: 'How it works',
  description:
    'One complete run of the Reasoner pipeline — its sources, its scores, the positions it discarded, and what it cost. A capture of the production code path, not a mockup.',
  alternates: { canonical: absoluteUrl('/how-it-works') },
  openGraph: {
    title: `How it works — ${SITE.name}`,
    description: 'One complete run of the pipeline, with nothing left out.',
    url: absoluteUrl('/how-it-works'),
    type: 'website',
  },
};

export default RunRecord;
