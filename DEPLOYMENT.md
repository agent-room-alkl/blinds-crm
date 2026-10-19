# Deployment

The root `vercel.json` routes `/api/*` to FastAPI and frontend pages, including `/portal`, to Vue. Use the Services preset with repository root `./`. Configure server variables from `backend/.env.example`; do not commit credentials.

## Persistence

Cloud runs require PostgreSQL with a dedicated `VERA_DB_SCHEMA` (default `vera`). System/public schemas are rejected. Keep `VERA_AUTO_INIT=0` on production cold starts. Configure the private R2 bucket for product images and retain database/media backups.

New database: `python backend/init_database.py`. Existing database: `python backend/migrate_operations.py` adds the current tables without deleting records. `migrate_sqlite_to_postgres.py` copies current domains to a NEW target schema, refuses existing targets, preserves operation JSON and excludes retired tables and sessions.

## Retired data cleanup

The app no longer creates or exposes contacts/inquiries/follow-ups/quotes/old orders/communications/workbench/AI tables or endpoints. Existing physical tables remain until an explicit migration is run.

Take a provider/database snapshot for full rollback. Run `python backend/cleanup_legacy.py` to review the fixed table names and counts. For the authorized deployment cleanup, run `python backend/cleanup_legacy.py --apply --backup <private-new-archive.json>`.

The apply command writes retired rows to a NEW private archive, drops only a fixed allowlist without CASCADE, removes customers unlinked to current portal/operations, and verifies current users/products/customers/sessions/projects unchanged in the same transaction. The JSON archive is supplementary row recovery, not a full PostgreSQL schema backup. Do not commit it. Cleanup is not invoked by startup. Preparing or reviewing this code does not imply live data has been removed.

## Private rules and email

An administrator uploads the current xlsm in Project orders. Only dictionaries and pricing go into the private database; source customer rows and VBA are not imported/executed. Check warnings and verify reference prices before operational use.

Email defaults to `VERA_EMAIL_MODE=demo`. Keep `VERA_DEMO_EMAIL_ADDRESS` private. Demo delivery becomes ready only with SMTP_HOST, SMTP_PORT, SMTP_SECURITY, and SMTP_FROM matching that same test address; optional SMTP username/password depend on the provider. Demo messages force both From and To to the test address even when a customer address is stored. Without a ready mail service, notification attempts are recorded as unsent and no SMTP connection opens. A future live mode requires an explicit server setting and operational approval. Arrival events create notifications after their batch is saved; invoice sending is explicit. Unconfigured/ambiguous delivery remains visible. The retired IMAP sync, AI drafting, inbox collection, webhook and cron settings are gone.

## Validation

Run the local suites in README and the frontend build. Optional `python backend/test_postgres.py` runs current auth/catalogue/R2 API checks in unique `vera_test_*` schemas and deletes only those test schemas; it requires configured test access. Never run application suites directly against production.

After an authorized deployment, check health, staff/customer separation, product prices, review/60% deposit, batch/notification status, balance/receipt records and XLSX output. Formal factory layout, partial-arrival invoicing and automatic rebate tiers remain dependencies.
