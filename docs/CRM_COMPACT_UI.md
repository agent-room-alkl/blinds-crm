# Compact CRM workspace

The order list keeps its batch-selection checkbox inside each order row. The checkbox has an 18 px visible control and a 44 px selection target; the rest of the row still opens the order. Long project names remain available as a tooltip.

The review card keeps the adjustment note, save action, and deposit-draft confirmation on one desktop row. The adjustment table scrolls within the card so the primary action remains visible at a 900 px desktop height.

Finance uses three desktop panels for source orders, invoices, and actions. Source and invoice lists scroll inside their panels. The action panel switches between balance, rebates, and notifications without lengthening the desktop page. At narrower widths, panels stack and the mobile navigation starts collapsed.

The layout was checked at 1440 × 900, 1920 × 886, and 390 px widths. At desktop sizes the finance panels and review actions remain within the viewport; no horizontal document overflow was observed. The frontend typecheck and production build pass with `npm run build`.
