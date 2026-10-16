# VERA Shading Solutions

Vue 3 + TypeScript and FastAPI customer portal/project operations. `/portal` is the customer entry; `/crm` is for employees. Support/History, inquiries, manual quotations, follow-ups and the old AI/mail workbench are removed from frontend and backend.

## Local development

Use `./dev.ps1 backend` and `./dev.ps1 frontend` in separate PowerShell terminals. The pair connects the frontend to port 8002. Keep unrelated processes running if a port is occupied.

Alternatively, install `backend/requirements.txt` into a Python virtual environment, run `uvicorn app.main:app --reload --port 8002` from `backend`, and run `npm install` / `npm run dev` in `frontend` with the matching proxy. Local SQLite is available without PostgreSQL configuration. Server settings load from ignored `.env` files. Initial local demo credentials are `dylan` / `vera-demo`; cloud initialization requires a configured password.

## Workflow

An administrator opens one account and one contact per company, then privately uploads the order workbook. The server extracts 23 product configurations and versioned area/matrix prices. The public catalogue shows five website shutter series; template-only products stay in the portal, and Ashwood is display-only without a confirmed price. Product IDs are not reused for different products.

Customers configure named windows, separating repeated-window quantity from panels per window. The server calculates installation, GST and ROUNDUP. Customers cannot enter prices or discounts. Employees review documented adjustments, freeze the order and create a **60% deposit** draft. Manual receipt, supplier reference, transit, partial arrival and delivery are separate actions. Batch operations report each result and reuse idempotency keys on retry.

Customer profiles are editable. Company records separate ordered, invoiced, manually confirmed received and invoiced-outstanding totals. Fully delivered orders can form same-company balance drafts, deducting saved deposits and confirmed rebate balances once. Production-information and job-sheet XLSX files come from the frozen order. Sending and payment confirmation are separate.

Real workbooks, private price matrices, extracted customer data and credentials are not committed to this public repository. Missing/invalid rules block pricing. ClearPVC has an unresolved installation alias; that installation quote is refused. Formal supplier layout, monthly rebate tiers, partial-arrival billing, refunds/corrections and final invoice format still require business rules. Dashboard figures are labelled examples.

## Database deployment and cleanup

New installation: `python backend/init_database.py`. Existing installation: `python backend/migrate_operations.py` adds current tables without deleting data. An administrator then uploads the workbook in CRM.

Retired Support/History tables are not created by the app. Remove existing copies using `backend/cleanup_legacy.py`: default is a count-only dry run; `--apply --backup <private-new-file.json>` archives retired rows and drops the fixed legacy table set plus unlinked legacy customers. Current products, users, sessions, portal customers and operations are verified unchanged. Keep the archive private and take a provider snapshot for full rollback. Cleanup is never a cold-start action. No live database has been cleaned or deployed by preparing this PR.

See [deployment](DEPLOYMENT.md), [API](backend/OPERATIONS.md) and [Excel automation](docs/CRM-excel-automation.zh-CN.md). Earlier source-review documents describe their original stage; this README and active API describe current behavior.

## Labelled local sample data

`python backend/seed_demo.py` creates (or reuses) only `backend/.demo/vera-demo.db`, with 3 demo companies and 7 projects spanning pending review, deposit, supplier order, transit, partial arrival/delivery and settled states. It uses invented prices, example.invalid contacts and disabled SMTP. It refuses an existing database without its demo marker and cannot write PostgreSQL. The local staff demo account uses the existing README demo credentials; customer `demo-trade` uses the explicitly non-production password `local-demo-only`.

To review it, launch the backend with `VERA_DB_BACKEND=sqlite`, `VERA_DB=<absolute backend/.demo/vera-demo.db>`, `VERA_STORAGE_BACKEND=local`, `SMTP_HOST=` and `SMTP_FROM=`. Point the frontend proxy to that local backend. This sample database is ignored by Git and never replaces operational data.

## Verification

- `python backend/test_core_api.py`: auth/users/settings, retired routes 404 and clean fresh schema.
- `python backend/test_legacy_cleanup.py`: isolated dry run/archive/removal and current-data preservation.
- `python backend/test_operations.py`: company isolation, 60%, batching, notification/invoice retries, receipts and settlement/rebate dedupe.
- `python backend/test_excel_rules.py`: invented price fixtures, formula engines, catalogue scope, private matrix hiding, exports, profiles and consumption. Optional `--source <local.xlsm>` checks local reference rows without publishing rates.
- `python backend/test_products.py`: catalogue/media permissions, validation, privacy and galleries.
- `npm run build` in `frontend`: TypeScript and production build.

Local backend suites use temporary SQLite databases and mocked external email. Optional PostgreSQL checks use uniquely named disposable test schemas; see DEPLOYMENT.md.
