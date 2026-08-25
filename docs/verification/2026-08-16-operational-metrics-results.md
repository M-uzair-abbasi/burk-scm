# Operational metrics verification — 2026-08-16

Task 6 is verified on PostgreSQL.

| Signal | Authoritative source | Result |
|---|---|---|
| Queue depth, oldest due, retry, failure | `operations.WorkItem` aggregates | Verified |
| Burk/Daraz source freshness/failures | append-only `orders.SyncRun` aggregates | Verified |
| Wrong-item and overscan interceptions | append-only `fulfillment.PackScan` aggregates | Verified |
| Delivery acknowledgement latency/failures | `notifications.Notification` aggregates | Verified |
| Courier booking failures | terminal `book_shipment` work items | Verified |
| Media processing duration/failures | `surveillance.PackagingRecording` aggregates | Verified |

The report executes five query groups regardless of event volume; a 200-row mismatch ledger stayed under the six-query test bound. Detailed metrics require a Manager. Operator access returns 403. Public health does not include the detailed report.

Evidence: 23 common tests passed; migration/check gates passed; TypeScript, ESLint, and the 11-route Next.js production build passed.
