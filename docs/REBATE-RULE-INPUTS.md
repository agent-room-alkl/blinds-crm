# Rebate automation: what exists and what is still missing

## What the source workbook contains
`Shutter Studio Wholesale Order Template - native repaired.xlsm` (sheets: In Put, Order, Product Listing, Pricing,
Wholesale Quote, Blinds Order, Shutter Order, Job Sheet) was searched for rebate/返利/返点/bonus/tier/volume/commission
terms in its shared strings and sheet XML: no hits. The only payment-related formula is the deposit,
`ROUNDUP(P49*0.6,2)` on the `In Put` sheet. Order discount options exist, but a discount is not a rebate and must not be
used as one. Not checked: the compressed VBA project inside the workbook.

## What the system does today
- Balance: `POST /api/operations/settlements` creates a **draft** invoice for fully delivered orders whose deposit is
  received (total minus stored deposit), then deducts confirmed rebate credits from earlier months. Sending is a separate step.
- Rebates: `POST /api/operations/rebates` records an **already confirmed** monthly amount with its evidence. Nothing is calculated.

## Needed before rebates can be calculated automatically
1. Basis: ordered, invoiced, paid or delivered amount?
2. Tax: amounts before or after GST?
3. Tiers: each threshold and its percentage, and whether a tier applies to the whole amount or only the part above it.
4. Period: calendar month or another cycle, and when the credit becomes usable.
5. Refunds and corrections: how a refunded or amended order reverses an earlier rebate.
6. Scope: per company, per product line, or both.
Once supplied, the tiers should be stored as editable parameters (not constants in code) and the monthly result written
through the existing rebate record so the audit trail stays the same.
