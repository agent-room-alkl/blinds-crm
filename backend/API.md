# VERA API

The current API is documented in [OPERATIONS.md](OPERATIONS.md).

Retained domains: staff auth/users, products/media, `/api/portal/*` and `/api/operations/*`. The previous inquiry, quotation, manual-order, follow-up, communication, AI and mail-sync APIs have been removed and return 404.

Create a new schema with `python backend/init_database.py`. Add current tables to an existing schema with `python backend/migrate_operations.py`.

Physical retired-data cleanup is explicit: `python backend/cleanup_legacy.py` prints a count-only plan. `--apply --backup <private-new-archive.json>` archives retired rows, drops only fixed legacy tables without CASCADE, removes unlinked legacy customers and verifies current records unchanged in one transaction. Use a provider snapshot for complete rollback. No live cleanup is performed by preparing this change.
