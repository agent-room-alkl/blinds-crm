# Customer portal / project operations contract

2026-10-16 revision: the client's 2026-10-15 reply corrects the earlier 20% planning figure to **60%**. New deposit drafts use `ROUNDUP(total * 0.60, 2)` from the supplied workbook's `In Put!P51` and save their rate/rounding/source. Existing invoice snapshots are never recalculated. The workbook also contains an older 50% block at `In Put!P36/Q36`; it must not override the client's explicit 60% correction.

The supplied workbook reveals two pricing methods: shutters use area rates, other blinds use width/drop matrices. The generic area rule below remains a configurable prototype, **not an implementation of the supplied workbook**. No workbook rates have been imported. Production configuration is blocked pending field/rule mapping and sample verification; see the 2026-10-16 source review under output.

Run `python backend/test_operations.py` with the backend virtual environment. It creates a temporary SQLite database and mocks email. Never point these checks at production.

Existing database: run `python backend/migrate_workflow.py` once during the normal reviewed deployment procedure. It adds portal/operations tables and verifies existing business counts; it does not delete historical contacts, quotes or orders. Fresh `init_database.py` also creates them. No migration or deployment to the live database has been performed as part of local development.

## Identity

Staff tokens remain `/api/auth/login` tokens. Portal tokens only authenticate `/api/portal/*`, and cannot access staff or old CRM APIs. Portal profiles have a primary key on customer_id and unique username; each profile has one contact_name/email/phone/company_address. Provision through staff-admin `POST /api/operations/customers`, optionally linking an existing customer_id. Historical multiple-contact rows remain historical; new portal operations use only the single portal profile.

`POST /api/portal/login {username,password}` → token; GET me, POST logout. GET catalog returns published product series with `price_rule` or null. GET orders and consumption are company-scoped.

## Orders and rules

`POST /api/portal/price` and `/api/portal/orders` accept project_name, site_address, submission_key and lines `{window_name, product_id, width_mm, height_mm, quantity, options}`. Orders with missing confirmed prices may be recorded as pending_review with total=null, but cannot be reviewed, invoiced or sent to the supplier. The price endpoint returns 409 until rules exist. No client unit_price is accepted.

Admin `POST /api/operations/pricing/{product_id}` accepts PriceRule in operations.py. Rules require evidence of the confirmed sheet, area/minimum/rounding/dimension limits, currency/tax_basis and exact option choices. The supported formula is explicitly selected: round dimensions upward by dimension_step_mm, area in m² subject to minimum; `(area * rate + sum fixed) * (1 + sum percent / 100) + sum installation`, rounded per unit then multiplied by quantity. An empty charge dictionary is a visual-only choice. This formula is an available configuration, **not a claim that the customer's unprovided sheet uses it**. No rules are seeded. Submit snapshots configured prices; review can price a previously unpriced pending order. Reviewed snapshots never change with the catalog.

Staff GET orders; POST orders/{id}/review generates one 60% deposit invoice draft; POST deposit-received records independent manual confirmation with actor/time. POST supplier-order `{reference}` requires that confirmation. Supplier Excel export returns 409 until the actual template/mapping is supplied; the recorded reference is not an Excel conversion.

POST transit `{order_ids,operation_key}` gives per-order success/failed/skipped. POST fulfilment `{order_id,kind:'arrival'|'delivery',operation_key,lines:[{line_id,quantity}]}` records the actual batch. Repeat identical operation keys do not duplicate; altered bodies conflict. Arrival ≤ ordered; delivery ≤ arrived. History keeps each batch; arrival_status/delivery_status/payment_status are separate. Frontend batch selection can submit per-order requests and display each outcome.

## Invoice, email and rebate boundaries

GET invoices, GET notifications; POST invoices/{id}/send explicitly sends a stable text invoice to the sole contact. This is a workflow prototype, not a confirmed statutory invoice layout/PDF. Arrival saves an outbox event then automatically attempts the email, showing only that batch. Statuses: pending/sending/sent/not_configured/delivery_unknown. Repeated calls never resend a sent or ambiguous email. POST notifications/{id}/retry is available after not_configured is fixed; ambiguous SMTP outcomes require manual mailbox reconciliation. A process interrupted while sending leaves `sending`, requiring that same reconciliation. Never label these as successfully sent.

POST rebates imports a confirmed monthly credit result with customer_id, source_order_ids, month, amount, currency and evidence. A source order cannot be counted again. There is no invented monthly ladder or automatic accrual formula. GET rebates explicitly reports confirmed_monthly_rules_required.

POST settlements takes order_ids, operation_key, rules_evidence and billing_basis=`fully_delivered_remaining_total`. It only supports fully delivered, deposit-confirmed projects of one company/currency/tax_basis; partial-arrival billing is blocked pending rules. It deducts each actual rounded deposit and eligible prior-month imported rebate balances under the explicit confirmed evidence; allocations and invoice claims are atomic. It never opens full balances merely because one batch arrived. Automatic monthly calculation, expiry/cancellation/refund rules, invoice correction/voiding, final receipt reconciliation and confirmed invoice layout remain dependent work. Do not describe the prototype as a complete production financial system.

Dashboard real analytics and customer ratings stay deferred per v5. The portal consumption response separates orders, invoices and credits and marks statistical basis as awaiting confirmation; no artificial spend/receipt aggregate is inferred.
