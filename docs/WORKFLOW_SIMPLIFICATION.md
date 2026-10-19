# Workflow simplification (T-28)

The interface follows the order's current stage. Selecting an order opens the relevant tab, shows a short next-step cue, and hides actions that cannot apply yet. Completing a stage refreshes the order and moves focus to the next one. Financial receipts, supplier placement, and message sending remain explicit because each records an external business event.

| Path | Before | Now |
| --- | --- | --- |
| Customer's first window | Choose series → open window list → add window → open configuration | Choose series → configure first window. Add another from configuration, reusing series and options. The list remains available for reviewing many windows. |
| Review and deposit | Find the review action among all order actions; switch tabs to find invoice and receipt | Pending orders open Pricing & review with its accept action. Acceptance creates the draft and opens Invoices & payments; a sole draft is selected. Receipt still requires confirmed funds and a click. |
| Supplier export | Choose supplier and template → save assignment → export | A sole active supplier and latest active template are suggested. Review the choice and download the Excel; export saves assignment in the same action. An unverified basic draft remains available if no approved layout exists. Supplier order reference is recorded separately after the supplier accepts it. |
| Transit, arrival, delivery | Navigate to fulfilment and enter each remaining quantity | The order opens its active stage. Transit has a single-order action. Arrival/delivery can fill the remaining quantities for review, then staff record the actual batch. |
| Balance and rebates | Navigate to finance, select company and source orders | Opening finance from an order selects the company. A sole eligible delivered order without a balance invoice is preselected. Confirmed-rule evidence and the final create action are still required. |

The backend still enforces 60% deposit, receipt before supplier ordering, active supplier/template for specific export, arrival/delivery bounds, same company/currency for settlement, frozen accepted prices, and idempotent financial records. The UI does not guess a formal factory worksheet, rebate tiers, a payment transaction, or an email recipient. Demo email remains owner-only and unconfigured SMTP means no delivery. The private test address is returned only to administrators; customer delivery requires a second explicit server flag as well as live mode.
