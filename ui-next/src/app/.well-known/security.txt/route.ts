import { absoluteUrl } from '@/lib/site';

/**
 * security.txt (RFC 9116) — the standard place a researcher looks for a
 * vulnerability-disclosure contact before trying anything more disruptive.
 *
 * `Expires` is a fixed date, not a rolling "one year from now": RFC 9116
 * requires ≤1 year out, and a fixed date is what makes an unmaintained file
 * visibly stale instead of silently claiming to be current forever. Renew
 * this alongside the yearly security review, or replace with an automated
 * check that fails CI once it is within 30 days of expiring.
 */
const EXPIRES = '2027-08-17T00:00:00.000Z';

export function GET(): Response {
  const body = [
    `Contact: ${absoluteUrl('/contact')}`,
    `Expires: ${EXPIRES}`,
    'Preferred-Languages: en',
    `Canonical: ${absoluteUrl('/.well-known/security.txt')}`,
    `Policy: ${absoluteUrl('/security')}`,
  ].join('\n');

  return new Response(`${body}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
