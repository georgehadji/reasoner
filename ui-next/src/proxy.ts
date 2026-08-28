import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { CSRF_COOKIE, CSRF_HEADER } from '@/lib/security-constants';
import { generateSignedCsrfToken, verifyCsrfToken } from '@/lib/security-server';
import { buildContentSecurityPolicy } from '@/lib/security-csp';
import { TIMING } from '@/lib/config';

const HSTS_VALUE = 'max-age=31536000; includeSubDomains; preload';

export async function proxy(request: NextRequest) {
  const response = NextResponse.next();

  const csp = buildContentSecurityPolicy({
    allowUnsafeEval: process.env.NODE_ENV !== 'production',
  });

  response.headers.set('Content-Security-Policy', csp);
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');

  if (process.env.NODE_ENV === 'production') {
    response.headers.set('Strict-Transport-Security', HSTS_VALUE);
  }

  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method)) {
    const header = request.headers.get(CSRF_HEADER) || '';
    const cookie = request.cookies.get(CSRF_COOKIE)?.value || '';
    if (!header || !cookie) {
      return new NextResponse(JSON.stringify({ error: 'Invalid or missing CSRF token' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const headerValid = await verifyCsrfToken(header);
    const cookieValid = await verifyCsrfToken(cookie);
    if (!headerValid || !cookieValid || header !== cookie) {
      return new NextResponse(JSON.stringify({ error: 'Invalid or missing CSRF token' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }
  }

  if (!request.cookies.get(CSRF_COOKIE)) {
    const token = await generateSignedCsrfToken();
    response.cookies.set(CSRF_COOKIE, token, {
      httpOnly: false,
      sameSite: 'strict',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: TIMING.csrfMaxAgeSeconds,
    });
  }

  return response;
}

export const config = {
  matcher: ['/api/:path*', '/((?!_next/|__webpack|favicon.ico|.*\\.).*)'],
};
