import { securityTxtLines } from '@/lib/security-txt';

/** security.txt (RFC 9116). Content and expiry policy: lib/security-txt.ts. */
export function GET(): Response {
  return new Response(`${securityTxtLines().join('\n')}\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
