import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusClient } from './StatusClient';

afterEach(() => vi.unstubAllGlobals());

function answer(body: unknown, status = 200) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

describe('StatusClient', () => {
  it('reads the verdict and each check from the health response', async () => {
    answer({
      status: 'degraded',
      checks: {
        memory: { status: 'ok' },
        circuit_breakers: { status: 'degraded' },
        postgres: { status: 'ok', reason: 'not configured' },
      },
    });
    render(<StatusClient />);

    expect(await screen.findByText('Degraded performance')).toBeTruthy();
    expect(screen.getByText('Model providers').nextSibling?.textContent).toBe('Degraded');
    expect(screen.getByText('Database').nextSibling?.textContent).toBe('Not configured');
  });

  it('says the API did not answer when the proxy reports it unreachable', async () => {
    answer({ status: 'unhealthy', error: 'Backend unreachable' }, 503);
    render(<StatusClient />);

    expect(await screen.findByText('The API did not answer')).toBeTruthy();
    expect(screen.getAllByText('Not checked')).toHaveLength(6);
  });
});
