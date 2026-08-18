'use client';

import useSWR from 'swr';
import { API } from '@/lib/config';
import { ProvenanceCapabilities } from '@/lib/types';

const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<ProvenanceCapabilities>;
};

const FALLBACK: ProvenanceCapabilities = {
  image_formats: [],
  pixel_backend_bound: false,
  layer_b_enabled: false,
};

/** What this deployment actually supports -- every provenance affordance
 * must gate on this rather than assuming a capability is bound. Fetched
 * once and cached; capabilities don't change within a session. */
export function useProvenanceCapabilities() {
  const { data, error, isLoading } = useSWR<ProvenanceCapabilities>(
    API.PROVENANCE_CAPABILITIES,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );
  return { capabilities: data ?? FALLBACK, error, isLoading };
}
