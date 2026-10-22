# Deploying audit 2 and audit 3

Steps to take when the audit-2 and audit-3 changes (PRs #143 to #165) reach an
environment. Every step comes from the two plans
(`docs/plans/audit-remediation-2-2026-10-20.md`,
`docs/plans/audit-remediation-3-2026-10-21.md`), the migration files and the
scripts named below. Nothing here has been run against a real deployment.
Do staging first, then production.

## 1. Before the deploy

1. **Back up the database.** Take a copy and run step 2 against the copy first
   (audit-2 Q1: the schema contract test only proves a clean database).
2. **Set `ADMIN_USER_IDS`** if admin routes are used. Admin now needs the JWT
   user id on this allowlist plus `X-Admin-Key`; API keys can never hold admin
   (`docs/ENVIRONMENT.md`).
3. **Multi-host only: confirm `data_dir` is a shared volume.** Neuro erasure
   markers are written to `<data_dir>/.erased` and each worker reads them there.
   On separate disks a marker written on one host is invisible to the others
   and erasure (DAT-13) does not hold.

## 2. Database migration

```bash
alembic upgrade head
```

Revisions that apply, in order:

| Revision | What it does |
|----------|--------------|
| `20261021_000000` | Credits keys and event constraints |
| `20261021_000001` | `subscriptions.last_event_at` |
| `20261021_000100` | `upload_usage` table |
| `20261021_000150` | Merge of the two heads above; changes no schema |
| `20261021_000200` | Webhook lease: `status` and `claimed_at` on `processed_webhooks` (creates the table if missing). Existing rows become `done` |

`alembic heads` must print one head (`20261021_000200`). Run it before the new
code serves traffic: the webhook handler reads the new columns.

## 3. Deploy the code

Rebuild the image (`docker build` has not been run on the lean-PR dependency
removals: import-linter and five transitive packages left `requirements*.txt`)
and run the smoke tests.

## 4. After the deploy

Do these in order, by a person.

1. **Upload usage.** Usage is now a counter that starts at zero for every user.
   Backfill it before relying on the quota:
   ```bash
   PYTHONPATH=src python scripts/backfill_upload_usage.py           # dry run
   PYTHONPATH=src python scripts/backfill_upload_usage.py --apply
   ```
2. **Stripe customer metadata.** Needs `DATABASE_URL` and `STRIPE_SECRET_KEY`.
   Dry run, read it, then apply (this writes to Stripe):
   ```bash
   python scripts/backfill_stripe_customer_metadata.py
   python scripts/backfill_stripe_customer_metadata.py --apply
   ```
3. **History layout.** Moves `history/<id>.json` to `history/<owner_key>/<id>.json`.
   Until the marker file `.layout-v2` exists the app still reads and erases
   the flat files, so there is no gap between deploy and migration:
   ```bash
   PYTHONPATH=src python scripts/migrate_history_layout.py           # dry run
   PYTHONPATH=src python scripts/migrate_history_layout.py --apply
   ```
   The marker is written only when every file moved. A file the script prints
   as `skip` could not be attributed to an owner; fix or remove it and re-run.
4. **Delete the old `history/*.jsonl` files.** They hold copies of every user's
   entries, nothing reads them any more, and the script only lists them. Delete
   them by hand after step 3.

## 5. What to tell users and watch

Changelog and API-user notes:

- Account deletion now also erases Neuro memory and stored runs, and the
  `DELETE /api/user/data` route erases everything except the profile and the
  sign-in identity.
- Data export returns more: profile, subscriptions, quota, query log, credit
  ledger, history entries, stored run events, Neuro memory entries and upload
  metadata. The uploaded files themselves are not included (audit-3 Q1).
- Resume and `run-with-context` are billed (audit 2).
- Agent and MCP clients now see real `total_cost_usd` and run errors; stopped runs
  no longer count as completed, so completion metrics drop by their number.
- `GET /api/neuro/health` stays public and now reports counts, not tenant keys
  (audit-3 Q4).

Watch for a week after deploy: fallback rate, cost per run, circuit-open events
(routing changed for about 43 role/preset pairs), runs-completed rate and method
mix.

## 6. Not verified

- A real Supabase sign-in against the new Content-Security-Policy. Test sign-in
  on staging before production; the CSP change is what makes it work.
- `docker build`.
- The rate limiter is not on `GuardedValkey`; there is no direct-vendor price
  table; 45 preset pairs stay over the fallback budget behind
  `MAX_IMPLICIT_OVER_BUDGET`.
