# Plan: email verification (row M10)

Date: 2026-11-12. Follows `docs/plans/implicit-state-machines-2026-11-11.md`
§1.2 row M10 and §5 question 3, where the user chose "plan an email
verification flow" over deleting the column.

## 0. Goal and the one decision

`users.email_verified` exists (`migrations/001_saas_init.sql:12`, Alembic
baseline `df9629e72f17`) but nothing writes it, so every row is `false` and
nothing reads it except the GDPR export (`user_data_pg.py:22`).

**The decision: Supabase stays the source of truth.** Supabase Auth already
sends the confirmation email at signup (the signup page says "Check your email
to confirm it", `ui-next/src/app/signup/page.tsx:157`) and records
`email_confirmed_at` on its user. We do not build our own token table, signed
links or mail template. We read the flag Supabase already has, mirror it into
our row, and gate the features that are worth gating.

Why this choice:

- **Less to own.** A home-grown flow needs a token store, expiry, rate limits,
  a template, a link handler and abuse handling. Supabase has all of these.
- **One truth.** Two verification systems can disagree. With one, the flag on
  the request is always the provider's current answer.
- **No new dependency.** `ResendEmailAdapter` stays for notifications only.

## 1. What exists today (VERIFIED in this repo)

| Piece | Where | State |
|---|---|---|
| Column | `users.email_verified BOOLEAN DEFAULT FALSE` | no writer |
| Domain user | `domain/saas.py` `User` | no verification field |
| Supabase adapter | `infrastructure/auth/supabase_adapter.py:77-118` | calls `auth.get_user(token)` on each authentication, maps id, email, provider, avatar; ignores `email_confirmed_at` |
| Local adapter | `infrastructure/auth/local_adapter.py` | dev JWTs from `create_token`; no verification claim |
| Provisioning | `api/dependencies.py` `_ensure_user_in_db` | upserts email, display name, provider, avatar, last login; not `email_verified` |
| Signup (UI) | `ui-next/src/lib/auth.ts:110` | `client.auth.signUp({ email, password })`, no `emailRedirectTo` |
| Supabase client | `ui-next/src/lib/supabase.ts` | implicit flow (auth-js default `flowType: 'implicit'`), `detectSessionInUrl: true`, so a confirmation link that lands on any app page signs the user in |
| What a new account gets | `domain/credits.py:34` | FREE tier: 500 credits a month |
| JS user type | `@supabase/auth-js` `User.email_confirmed_at?: string` | present |

**UNKNOWN, needs the user:**

- **"Confirm email" is off** in the Supabase project's Auth settings (the user's answer, 2026-11-12). Supabase still sends the confirmation email, but it gives a session at once, so an unconfirmed address can use the app straight away and gets the 500 free credits a month. Throwaway signups are a live credit-farming path today, which makes step 3 the point of this plan. Turning the setting on is the other option: it blocks the first login until the link is clicked, with no code change, but it also stops new users from trying the app before they confirm. This plan keeps it off and gates only the credit grant and API keys.
- **INFERENCE:** the Python `supabase-auth` user model has the same `email_confirmed_at` field as the JS one. The package is not installed in this checkout, so check it before step 1.
- **HYPOTHESIS:** OAuth signups (Google, GitHub) come back with `email_confirmed_at` set when the provider vouches for the address. Check this against a real OAuth login before you rely on it.

## 2. The machine

`email_verification`, observe mode, built in `infrastructure/auth/` (since `domain/` cannot import `core.state_machine`):

```
unverified -> verified      (link clicked, or OAuth provider vouched)
verified   -> unverified    (email changed; Supabase keeps the old address until the new one is confirmed, so this is rare)
```

It has no terminal state. That breaks the soundness check in `tests/architecture/test_state_machines.py`, which requires a reachable terminal state. There are two fixes:

- add `deleted` as the terminal state, reached when the account is deleted (recommended, because it matches M7); or
- let the soundness test accept a machine marked `cyclic=True`.

## 3. Steps

Each step is a small PR. Order matters: read the flag, then mirror it, then observe, then enforce.

1. **Read the flag (backend).** Done 2026-11-12, `tests/test_email_verified_flag.py`. A Supabase user with no `email_confirmed_at` field counts as unverified (fail closed). A naive timestamp is taken as UTC.
   - Add `User.email_verified: bool = False` to `domain/saas.py`.
   - `SupabaseAuthAdapter._verify` sets it to `supabase_user.email_confirmed_at is not None`.
   - `SupabaseAuthAdapter._verify` also maps `created_at` from `supabase_user.created_at`. Today it is not mapped, so `User.created_at` defaults to the time of the request. The grandfather rule in step 3 needs the real signup time.
   - `LocalAuthAdapter` reads an `email_verified` claim. `create_token(..., email_verified=True)` is the dev default, so local development is never blocked.
   - Tests: one adapter test each for confirmed and not confirmed, with the Supabase response mocked.

2. **Mirror it into the row.** Done 2026-11-12, `tests/integration/test_email_verified_pg.py`. Its first run found that the upsert had always written a `display_name` column no migration created, so provisioning failed on every migrated database; migration `20261112_000700` adds the column.
   - `_ensure_user_in_db` writes `email_verified = EXCLUDED.email_verified` in its existing upsert. That is one column added to one statement; no migration is needed.
   - **No backfill.** A gate reads the flag from the request's `User`, which comes fresh from Supabase on every authentication, not from the row. The row is for admin, analytics and the GDPR export, and it fills in on each user's next login.
   - Test: the live Postgres provisioning test (`tests/integration/`, container on :55499) asserts the column follows the flag in both directions.

3. **Gate, in observe mode first.** Done 2026-11-12, `tests/test_email_verification_gate.py`.
   - The policy is `application/services/email_verification.py` (`email_gate_allows`). The grant check is `api/dependencies.allowance_permitted`, used by both grant call sites (`_top_up_allowance` and `GET /api/credits`). Key creation is refused in `api/routes/account_keys.py`.
   - **API key callers:** `_load_user_by_id` now carries `email_verified` and `created_at` from the row, which it used to drop. So a key caller keeps its account's status and signup time. Legacy keys count as verified, since they are operator-issued and have no address.
   - **No `email_verification` Machine (a change from §2).** The app never writes this state; it only copies the provider's flag, so a transition table would have no move to check. `reasoner_unverified_access_total` is the signal step 5 needs.
   - **Counting in enforce mode:** a refused grant is not cached, so `GET /api/credits` and `require_credits` count a denied hit on every request until the email is verified. Read the counter as attempts, not users.
   - Add one helper next to the other admission checks: `require_verified_email(user, feature)`. Under a new setting `EMAIL_VERIFICATION_MODE=observe|enforce` (default `observe`):
     - **observe:** it logs and counts `reasoner_unverified_access_total{feature}` and allows the request;
     - **enforce:** it raises a 403 with the code `email_unverified`.
   - **Grandfathering (user's answer, 2026-11-12):** an account created before `EMAIL_VERIFICATION_CUTOFF` (a new UTC timestamp setting, set to the moment enforce is switched on) passes without verification. The check is `user.email_verified or user.created_at < cutoff`. With no cutoff set, nobody is grandfathered, which is what observe mode needs to count real traffic.
   - **Gated features (user's answer, 2026-11-12):**
     - **Monthly free-credit grant** (`CreditService` grant path): no grant until verified. This is what stops credit farming.
     - **API key creation:** a key outlives the browser session, so it should belong to a confirmed address.
   - **Not gated:**
     - Paid checkout: Stripe and PayPal collect a real payer.
     - Account deletion: GDPR must always work.
     - Login.
     - Reading your own data.
   - Tests: each gated feature gets one test for observe (allowed and counted) and one for enforce (403 `email_unverified`).

4. **UI.**
   - `signUpWithEmail` passes `options: { emailRedirectTo: window.location.origin + '/chat' }`, so the link returns to the app instead of the Supabase Site URL. `detectSessionInUrl` already finishes the sign-in, so no callback route is needed.
   - The auth store keeps `emailVerified` from the Supabase session's `user.email_confirmed_at`.
   - A small banner component (tokens only, `role="status"`) shows for signed-in unverified users. It has a **Resend** button that calls `supabase.auth.resend({ type: 'signup', email })` through the existing `useAsyncAction` hook (one pending send, bfcache safe). Supabase rate-limits resends.
   - The API client maps a 403 with `email_unverified` to that banner, not to a generic error.
   - **Runs are not gated, but in practice they stop.** An unverified user gets no free credits, so their first run returns 402 (insufficient credits). For an unverified user, that 402 must show the verify banner ("Confirm your email to get your 500 free credits"), not the buy-credits prompt. The backend adds `email_unverified: true` to the 402 body so the UI can tell the two apart.
   - Tests (vitest): the banner shows only when unverified, Resend cannot double-send, the 403 code shows the banner, and a 402 with `email_unverified` shows the banner instead of the buy prompt.

5. **Enforce.**
   - After one release in which `reasoner_unverified_access_total` has been read and each hit explained, set `EMAIL_VERIFICATION_MODE=enforce`.
   - Set `EMAIL_VERIFICATION_CUTOFF` in the same deploy. Accounts that already exist keep their credits and keys; only accounts created after it must verify.

## 4. Open questions for the user

1. ~~**Supabase "Confirm email" setting.**~~ Answered: off. Step 3 is needed.
2. ~~**What to gate.**~~ Answered (2026-11-12): the free-credit grant and API key creation only. Runs are not gated directly.
3. ~~**Existing accounts.**~~ Answered (2026-11-12): grandfathered by signup time (step 3).

## 5. What this plan does not do

- **No custom verification emails, tokens or templates.** Supabase sends and checks them.
- **No change to the local adapter's security model.** It stays a dev-only path.
- **No migration.** The column already exists.

## 6. Done means

- The column is `true` exactly when Supabase says the address is confirmed, checked by a live Postgres test.
- In enforce mode, every gated feature returns 403 `email_unverified` for an unconfirmed address created after the cutoff, and allows one created before it, with one test per feature for each case.
- An unverified user sees the banner and can resend, checked by vitest.
- Gates: the fast lane, vitest, `tsc`, both `.importlinter` contracts, and every ratchet unchanged or lower.
