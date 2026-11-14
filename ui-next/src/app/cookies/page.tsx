import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import {
  ArgumentBody as Body,
  ArgumentSection as Section,
  BODY,
  CAP,
  FIGURE,
  HEAD,
  More,
  ROW,
} from '@/components/site/ArgumentSection';
import { STORAGE_KEYS, TIMING } from '@/lib/config';
import { PILOT_DRAFT_KEY } from '@/lib/pilot-draft';
import { CSRF_COOKIE, CSRF_HEADER } from '@/lib/security-constants';

/**
 * /cookies in the site world "The product performs".
 *
 * The page is an inventory, set the way a browser's own storage panel sets
 * it: one cookie, then every key the app keeps in browser storage. Names and
 * lifetimes are imported from the constants the code uses, so the page
 * cannot name a cookie the app does not set.
 *
 * Audited 2026-11-14: the only `cookies.set` in ui-next is the CSRF token
 * (`proxy.ts`, `app/api/csrf/route.ts`); the backend sets none. Sign-in is
 * held by supabase-js in localStorage, not in a cookie. No analytics,
 * advertising or third-party scripts are loaded; fonts are self-hosted.
 */

const CSRF_HOURS = TIMING.csrfMaxAgeSeconds / 3600;

const COOKIE = [
  { term: 'Name', value: CSRF_COOKIE },
  { term: 'Set by', value: 'This site, on your first visit' },
  { term: 'Lifetime', value: `${CSRF_HOURS} hours, then replaced` },
  { term: 'SameSite', value: 'Strict' },
  { term: 'Secure', value: 'Yes, over HTTPS' },
  { term: 'HttpOnly', value: 'No: the page must read it' },
  { term: 'Holds', value: 'A random token and its signature' },
];

const JOURNEY = [
  'Your first visit sets the token as a cookie.',
  `The page reads it and sends it back in an ${CSRF_HEADER} header with every change it asks for.`,
  'The server checks the signature on both copies and that the two match.',
  'A request from another site cannot read the cookie, so it cannot send the header, and is refused.',
];

/** Every key the app keeps in browser storage. The IndexedDB name is built in `lib/db.ts`. */
const STORED = [
  { key: 'sb-…-auth-token', where: 'localStorage', holds: 'Your sign-in session, kept by Supabase' },
  { key: 'theme', where: 'localStorage', holds: 'Light, dark or system appearance' },
  {
    key: STORAGE_KEYS.appStore,
    where: 'localStorage',
    holds: 'Plan, expert mode, western-only, sidebar, recent commands',
  },
  { key: STORAGE_KEYS.featureFlags, where: 'localStorage', holds: 'Features switched on for testing' },
  { key: PILOT_DRAFT_KEY, where: 'sessionStorage', holds: 'A pilot request carried to the contact form' },
  { key: 'ARA_Pipeline_v2_…', where: 'IndexedDB', holds: 'Your conversation history, one store per account' },
];

const ABSENT = [
  'Analytics or usage-tracking cookies',
  'Advertising or retargeting cookies',
  'Third-party scripts that set their own',
  'A consent banner, because none of the above is here',
];

export default function CookiesPage() {
  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {/* ── Hero: the claim (left), the one cookie as a browser shows it (right) ── */}
        <header className="grid min-h-[var(--site-hero-h)] lg:grid-cols-2">
          <div className="flex flex-col justify-end px-[var(--site-margin)] pb-[var(--space-12)] pt-[var(--space-32)] lg:pb-[var(--space-16)]">
            <h1 className="font-display text-[length:var(--site-display)] leading-[var(--site-lh-display)]">
              <span className="site-line">
                <span>One cookie,</span>
              </span>
              <span className="site-line">
                <span>and why.</span>
              </span>
            </h1>
            <div className="site-after-headline">
              <p className="mt-[var(--space-8)] max-w-[40ch] text-[length:var(--site-lead)] leading-[var(--site-lh-body)]">
                Reasoner sets a single cookie, to stop other sites making requests in your name. It tracks
                nothing and expires in {CSRF_HOURS} hours.
              </p>
              <p className={`mt-[var(--space-4)] max-w-[52ch] ${BODY}`}>
                What the app keeps in your browser&rsquo;s own storage is listed below too, key by key.
              </p>
              <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
                <a href="#storage" className="site-button">
                  See everything stored
                </a>
                <Link href="/privacy" className={`site-link ${BODY}`}>
                  Read the privacy policy
                </Link>
              </div>
            </div>
          </div>

          <div className="flex min-w-0 items-center justify-center bg-[var(--site-surface)] px-[var(--site-margin)] py-[var(--space-16)] lg:pt-[var(--space-24)]">
            <figure
              data-ui
              className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
            >
              <figcaption className={CAP}>Cookies set by this site: 1</figcaption>
              <dl>
                {COOKIE.map(({ term, value }) => (
                  <div key={term} className={`grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-[var(--space-3)] ${ROW}`}>
                    <dt className="text-[var(--site-muted)]">{term}</dt>
                    <dd className={term === 'Name' ? 'font-semibold' : ''}>
                      {term === 'Name' ? <code>{value}</code> : value}
                    </dd>
                  </div>
                ))}
              </dl>
            </figure>
          </div>
        </header>

        <Section
          id="csrf"
          lines={['What the cookie', 'is for.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>How the token travels</figcaption>
              <ol className="list-none">
                {JOURNEY.map((step, i) => (
                  <li key={step} className={`grid grid-cols-[auto_minmax(0,1fr)] gap-[var(--space-3)] ${ROW}`}>
                    <span className="font-semibold nums-tabular">{i + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </figure>
          }
        >
          <Body>
            Cross-site request forgery is a page on another site that quietly asks your browser to send a
            request here, carrying whatever this site already trusts. The token stops it: a change is
            only accepted when the request carries the same signed token in a header, and only a page
            served from this site can read the cookie to put it there.
          </Body>
          <Body>
            It is not HttpOnly for that reason. It holds no account, session or personal data, so reading
            it gives nothing away.
          </Body>
        </Section>

        <Section
          id="storage"
          lines={['The rest stays', 'in your browser.']}
          field
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Browser storage, by key</figcaption>
              <ul className="list-none">
                {STORED.map(({ key, where, holds }) => (
                  <li key={key} className={ROW}>
                    <p className="flex flex-wrap items-baseline justify-between gap-x-[var(--space-3)]">
                      <code className="font-semibold">{key}</code>
                      <span className="text-[var(--site-muted)]">{where}</span>
                    </p>
                    <p className="mt-[var(--space-1)] text-[var(--site-muted)]">{holds}</p>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            Browser storage stays on your device and is never sent with a request by itself. The app reads
            it to keep you signed in, remember how you set the interface, and show your past
            conversations without asking the server again.
          </Body>
          <Body>
            Signing out removes the session. Clearing this site&rsquo;s data in your browser removes all of
            it; your runs stay on your account until you erase them.
          </Body>
          <More href="/privacy">What the server keeps</More>
        </Section>

        <Section
          id="absent"
          lines={['What is not', 'here at all.']}
          figure={
            <figure data-ui className={FIGURE}>
              <figcaption className={CAP}>Not set on this site</figcaption>
              <ul className="list-none">
                {ABSENT.map((item) => (
                  <li key={item} className={`grid grid-cols-[minmax(0,1fr)_auto] gap-[var(--space-3)] ${ROW}`}>
                    <span>{item}</span>
                    <span className="text-[var(--site-muted)]">None</span>
                  </li>
                ))}
              </ul>
            </figure>
          }
        >
          <Body>
            The site loads no analytics, advertising or tracking scripts, and its fonts are served from
            this site. Errors are reported to our error monitor, which sets no cookie.
          </Body>
          <Body>
            When you pay, Stripe or PayPal takes you to its own pages, which set cookies under its own
            policy.
          </Body>
        </Section>

        <Section id="control" lines={['Blocking it', 'breaks one thing.']} field>
          <Body>
            Block the cookie and you can still read every page, but the app refuses anything that changes
            state, a run included, with an invalid-token error. Allow cookies for this site alone and it
            works again.
          </Body>
          <Body>
            Because the one cookie is strictly necessary and nothing here tracks you, there is nothing to
            opt out of.
          </Body>
        </Section>

        {/* ── Close ── */}
        <section aria-labelledby="close-h" className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] py-[var(--space-24)]">
          <h2 id="close-h" className={HEAD}>
            <span className="block">A cookie you</span>
            <span className="block">did not expect?</span>
          </h2>
          <p className={`mt-[var(--space-6)] max-w-[52ch] ${BODY}`}>
            Tell us its name. If this page missed it, the page is wrong and we will fix it.
          </p>
          <div className="mt-[var(--space-8)] flex flex-wrap items-center gap-x-[var(--space-8)] gap-y-[var(--space-4)]">
            <Link href="/contact" className="site-button">
              Get in touch
            </Link>
          </div>
          <p className={`mt-[var(--space-12)] text-[var(--site-muted)] ${BODY}`}>
            Effective [INPUT REQUIRED: effective date of this policy].
          </p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
