import { describe, expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import { GET } from './route';

const call = (loc: string) =>
  GET(new NextRequest(`http://localhost/api/weather?location=${encodeURIComponent(loc)}`));

describe('weather location validation', () => {
  it('rejects a location that merely contains a valid character', async () => {
    const res = await call('Paris<script>');
    expect(res.status).toBe(400);
  });
});
