# Order progress and compact detail navigation

The customer portal timeline derives progress from the statuses returned by the current operations API (`accepted`, `supplier_ordered`, fulfilment states, and payment states). Deposit and balance invoice milestones use actual invoice records. Completed and current markers therefore stay green for an accepted order instead of falling back to all gray.

The CRM removes the persistent demo-mail banner from the order workspace. Mail configuration and sandbox behavior remain visible in Settings and the operating guide. The list card and detail card start at the same vertical position. Order number and company share one line in the list and detail header.

The order detail navigation keeps Lines & fulfilment together. The next-step hint sits beside the navigation on wide screens and wraps below it on narrower screens. At 1440 px the list and detail cards both start at y=94.8; at 390 px the document scroll width remains 375 px. The left order list has explicit Previous/Next page controls and displays the current page and item range.
