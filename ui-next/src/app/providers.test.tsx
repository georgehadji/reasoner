import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

/**
 * Decision Q9: the pre-UI-5 shared history database is cleared on load. The
 * call sat after the "no Supabase" early return, so a deployment without auth
 * kept the ownerless database forever.
 */

vi.mock('@/lib/supabase', () => ({ supabase: null }));
vi.mock('@/lib/db', () => ({
  clearLegacyHistory: vi.fn(async () => {}),
  deleteHistory: vi.fn(async () => {}),
  setHistoryOwner: vi.fn(),
}));

import { Providers } from './providers';
import { clearLegacyHistory } from '@/lib/db';

describe('Providers without Supabase', () => {
  it('still clears the legacy shared history database', () => {
    render(<Providers><div /></Providers>);
    expect(clearLegacyHistory).toHaveBeenCalledTimes(1);
  });
});
