# VERA Shading Solutions

Vue 3 + TypeScript and FastAPI customer portal/project operations. `/portal` is the customer entry; `/crm` is for employees. Support/History, inquiries, manual quotations, follow-ups and the old AI/mail workbench are removed from frontend and backend.

## Local development

Use `./dev.ps1 backend` and `./dev.ps1 frontend` in separate PowerShell terminals. The pair connects the frontend to port 8002. Keep unrelated processes running if a port is occupied.

The current local and online app share the configured PostgreSQL `vera` schema. `backend/start_current.ps1` starts the local API on port 8002 with SMTP disabled for simulated workflows. There is no active SQLite application database. Connection values load from ignored `.env` files. See [current dataset and migration](docs/CURRENT_DATABASE.md).

## Workflow

An administrator opens one account and one contact per company, then privately uploads the order workbook. The server extracts private versioned workbook rules. Public and portal catalogues both offer exactly five website series: Eco, Classic, Natural, Prime and Deluxe, with the official website images. Aluminium and blind codes are excluded from customer ordering. Deluxe remains explicitly provisional until its commercial rate is confirmed. Product IDs are not reused for different products.

Customers configure named windows, separating repeated-window quantity from panels per window. The server calculates installation, GST and ROUNDUP. Customers cannot enter prices or discounts. Employees review documented adjustments, freeze the order and create a **60% deposit** draft. Manual receipt, supplier reference, transit, partial arrival and delivery are separate actions. Batch operations report each result and reuse idempotency keys on retry.

Customer profiles are editable. Company records separate ordered, invoiced, manually confirmed received and invoiced-outstanding totals. Fully delivered orders can form same-company balance drafts, deducting saved deposits and confirmed rebate balances once. Production-information and job-sheet XLSX files come from the frozen order. Sending and payment confirmation are separate.

Real workbooks, private price matrices, extracted customer data and credentials are not committed to this public repository. Missing/invalid rules block pricing. ClearPVC has an unresolved installation alias; that installation quote is refused. Formal supplier layout, monthly rebate tiers, partial-arrival billing, refunds/corrections and final invoice format still require business rules. Dashboard figures are labelled examples.

## Database deployment and cleanup

New installation: `python backend/init_database.py`. Existing installation: `python backend/migrate_operations.py` adds current tables without deleting data. An administrator then uploads the workbook in CRM.

Retired Support/History tables are not created by the app. Remove existing copies using `backend/cleanup_legacy.py`: default is a count-only dry run; `--apply --backup <private-new-file.json>` archives retired rows and drops the fixed legacy table set plus unlinked legacy customers. Current products, users, sessions, portal customers and operations are verified unchanged. Keep the archive private and take a provider snapshot for full rollback. Cleanup is never a cold-start action. No live database has been cleaned or deployed by preparing this PR.

See [deployment](DEPLOYMENT.md), [API](backend/OPERATIONS.md) and [Excel automation](docs/CRM-excel-automation.zh-CN.md). Earlier source-review documents describe their original stage; this README and active API describe current behavior.

## Current shared data

The owner-approved shared dataset has 19 workbook customer companies, five website products and seven explicitly simulated orders. Missing source contact/address fields remain marked missing. Two payment/quotation issuers are inactive candidates whose role as factory suppliers is unconfirmed. Real contacts and rates stay private. Old demo/test databases were removed. Temporary database fixtures inside automated tests remain isolated.

`seed_current.py` and `replace_current_postgres.py` support a future explicitly authorized rebuild/migration; they are not startup commands. Start the current app with `./dev.ps1 backend` and `./dev.ps1 frontend`.

## Verification

- `python backend/test_core_api.py`: auth/users/settings, retired routes 404 and clean fresh schema.
- `python backend/test_legacy_cleanup.py`: isolated dry run/archive/removal and current-data preservation.
- `python backend/test_operations.py`: company isolation, 60%, batching, notification/invoice retries, receipts and settlement/rebate dedupe.
- `python backend/test_excel_rules.py`: invented price fixtures, formula engines, catalogue scope, private matrix hiding, exports, profiles and consumption. Optional `--source <local.xlsm>` checks local reference rows without publishing rates.
- `python backend/test_products.py`: catalogue/media permissions, validation, privacy and galleries.
- `npm run build` in `frontend`: TypeScript and production build.

Local backend suites use temporary SQLite databases and mocked external email. Optional PostgreSQL checks use uniquely named disposable test schemas; see DEPLOYMENT.md.
