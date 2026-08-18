import type { Metadata } from 'next';
import { FxLab } from './FxLab';

/** Internal design lab. Never indexed, never linked from nav. */
export const metadata: Metadata = {
  title: 'FX Lab',
  robots: { index: false, follow: false },
};

export default function FxLabPage() {
  return <FxLab />;
}
