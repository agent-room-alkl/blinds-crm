# CRM navigation proposal

Status: approved by Robin and implemented in T-22, 19 October2026. The design below records the agreed ownership model.

Implementation: independent /crm/projects, /crm/customers, /crm/providers, /crm/pricing and /crm/finance routes; shared ProjectDesk controller renders only its explicit workspace, with no unrelated order list on resource pages. Customer account creation and selected-customer account details live in PortalCustomers, with search and five-row pagination. Price versions expose actual rule_version order usage and separately configured supplier applicability; export revisions are new immutable rows with metadata in operations_records. Supplier assignment/export history records the exact selected revision and mappings. No new database or business-table schema is introduced. Existing historical export revisions remain explicitly unspecified.

Validation: seven backend suites and frontend typecheck/build pass. New operations assertions cover duplicate-company rejection, bounded/idempotent order numbers, price usage and supplier applicability, activation preserving all orders, immutable export revisions and export audit surviving reassignment. Actual shared-PG UI checks verify standalone supplier/pricing/finance pages and exact order-reference navigation. At1440x900 the pricing page with9 references and the customer account page both have scrollHeight900; at390px the pricing/order pages have no horizontal overflow and visible buttons meet44px minimum. Screenshots and test logs remain local under output/t22 and output/t19; customer data is not committed.

## What the current code actually does

CrmView already has Customers, but account creation lives separately in ProjectDesk. ProjectDesk mounts Pricing, Customers, Providers, Batch and Settlement next to one selected order. This makes global actions appear scoped to that order. Provider rows and provider templates are global; order_providers is the separate order assignment relation. Pricing imports are global, stored by workbook content version with one active pointer. Order lines already retain rule_version and private price_snapshot. Existing provider export templates have provider ownership and order assignments but lack explicit immutable revision history. Rebates are customer/month/source-order records; balance invoicing can span fully delivered orders of one company.

## Proposed primary navigation

| Left navigation | Content and ownership |
| --- | --- |
| Orders | Order list, filters, selected-order workflow, selection-based batch actions |
| Customers | Company/contact/address, portal account management, order and financial summaries |
| Suppliers | Shared supplier identity, contact, active state, supported products and export-template revisions |
| Pricing & templates | Shared pricing workbook versions, activation, applicable products/suppliers, usage history |
| Accounts & rebates | Invoice/receipt lists, customer settlement, confirmed monthly rebate ledger and usage |
| Product catalogue | Five website series, descriptions, images, publication state |
| Analytics | Existing dashboard; metrics link back to source lists |
| Settings | Staff users/roles, integrations and system settings |

Every primary module should have its own route and page title. Supplier/pricing/finance pages must not retain an unrelated selected-order sidebar. Order lists should have a filter/search toolbar and compact rows, with an intentional detail pane when an order is selected.

## Selected-order workspace

Header: readable order number, project, company, current workflow stage and allowed next action. Sections: Overview & windows; Pricing & review; Purchasing & supplier; Arrival & delivery; Invoices & receipts; Activity.

Pricing & review shows this order's applied price version, calculation summary, provisional warnings and pre-acceptance adjustments. It links to the shared version; it does not import or activate a global workbook. Purchasing & supplier selects an existing active supplier and one of its export-template revisions, records supplier reference and export history, and supports one or more assigned suppliers using the existing relation. Adding/editing a shared supplier opens the Suppliers page and returns to the order.

Single-order invoice actions and receipt confirmation stay available in context. Cross-order balance invoicing and monthly rebate recording belong in Accounts & rebates. The order shows related invoices, rebate allocations and links. Batch transit/arrival actions appear when rows are selected, with selected count, eligibility checks and per-order outcomes; they are not a permanent tab inside an unrelated selected order.

## Customer account placement

One customer detail page owns tabs for Profile; Portal account; Orders; Accounts & rebates. Preserve the current one account/one contact rule. Account creation belongs here and is bound to customer_id; it must not create a second company/contact record accidentally. Show username/status, never an existing password. Credential-change behavior and permissions require a separate explicit design; do not invent a currently unsupported reset feature as part of moving forms. Missing source email/address remains marked missing; moving UI must not make fabricated contact details mandatory.

## Two different template concepts

Pricing workbook: shared commercial rule version, product scope, source filename, import time, activation state, and independently configured applicable suppliers. Supplier export template: supplier-owned sheet and column mappings with immutable revision identity. They may come from the same Excel file but represent different responsibilities and must be labelled separately.

Pricing version detail shows exactly which orders/lines used it, grouped counts and clickable order numbers, plus explicitly configured supplier applicability. Existing rule_version snapshots support order usage lookup. Do not infer supplier applicability from a workbook payment issuer or from the fact that an order happened to use that version. Historical unknown associations display Unspecified.

Supplier detail shows export-template revisions, assigned orders, and applicable pricing versions. An order's supplier assignment records the chosen export revision. Changes create a new revision; historical exports retain revision and export time. Pricing activation affects future calculations; accepted orders remain frozen. Any repricing of an unaccepted order is explicit and logged.

Disable/archive referenced resources instead of deleting them. Reference counts link to the exact records. A global activation/change form states its scope before saving. A supplier change on an order affects that assignment only and does not change global supplier defaults or historical exports.

## Finance and rebate boundaries

Accounts & rebates offers Invoices; Receipts; Customer settlement; Rebates. Require one company and currency for cross-order settlement. Keep existing delivered/deposit-received eligibility checks, frozen deposit deduction, idempotency and duplicate-source protection. Rebate ledger shows customer/month, confirmed amount, source orders, approval evidence, used/remaining and invoice allocation history. No automatic rebate tiers until the commercial formula is supplied. Customer and order views link to this same ledger rather than maintaining duplicate balances.

## Delivery phases and acceptance

1. Move existing customer-account form into Customers. Extract shared supplier, pricing and finance components from ProjectDesk into dedicated routes/nav; preserve API semantics. Keep order-specific supplier assignment/export and invoice actions in Orders. Verify a global screen remains correct when the selected order changes or there are zero orders.
2. Add explicit template version/detail/usage endpoints. Pricing order usage reads saved line rule_version, not the latest active pointer. Add supplier applicability and immutable export revisions with historical unknown values preserved. Existing assignments remain usable without inventing revision facts.
3. Consolidate settlement/rebate workflows, source-order navigation and selection-based batch actions. Verify company/currency boundaries, duplicate protections, permissions, readable numbers and frozen historical prices.

Acceptance: no global management tabs inside an order; one customer identity/account record; shared resources accessible with zero orders; exact bidirectional order/template/supplier links; no old price or export revision overwritten; no additional database; 1440 desktop and390 mobile retain readable layout and44px controls. Refactor UI first, then add relationship/versioning capabilities under separately scoped tasks.
