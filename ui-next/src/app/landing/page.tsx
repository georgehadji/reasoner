import { permanentRedirect } from 'next/navigation';

/**
 * `/landing` used to serve a byte-identical copy of `/` — an unlisted duplicate
 * with no canonical, which splits ranking signals between two URLs for the same
 * page. A 308 to the real home page consolidates them without 404ing anything
 * that already links here.
 */
export default function LandingRedirect(): never {
  permanentRedirect('/');
}
