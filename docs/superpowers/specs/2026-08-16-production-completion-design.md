# Burk SCM Production Completion Design

**Date:** 2026-08-16  
**Status:** Proposed for implementation  
**System:** Burk.pk Automated Supply Chain and Smart Order Verification System

## 1. Goal and definition of complete

This work turns the existing integrated application into a production-capable SCM system without rewriting its working module boundaries. Completion has two independently reported states:

1. **Code-complete:** every locally controllable requirement in this specification is implemented, covered by PostgreSQL tests, and passes the documented automated and browser acceptance gates.
2. **Live-complete:** every external adapter has also passed its staging and production acceptance tests using Burk-approved credentials, endpoints, courier accounts, WhatsApp sender, SMTP provider, camera hardware, storage, and deployment infrastructure.

Code-complete must never be presented as live-complete. A simulated adapter may prove the internal contract but may not satisfy a live-integration acceptance gate. Missing credentials or external access are reported as explicit external blockers, not hidden behind a passing simulated test.

The project documentation will identify the system as an operational Burk.pk SCM project. It will not describe it as an FYP.

## 2. Delivery strategy

The current Django/DRF, PostgreSQL, Next.js, session-authentication, adapter, and append-only-ledger architecture remains in place. Work proceeds in five sequential gates:

1. Core data and workflow integrity.
2. Authorization and administrative safety.
3. Reliable asynchronous processing, media security, and observability.
4. Real external integrations.
5. Production acceptance and deployment readiness.

Each gate is divided into independently testable subtasks. A gate is not complete until its focused tests, the full regression suite, database integrity commands, and relevant frontend checks pass. No proactive Git commit is part of the workflow; commits remain controlled by the user.

## 3. Module 0 — foundations, authentication, and production configuration

### 3.1 Role and permission model

The supported roles remain Manager and Operator.

- A Manager can configure products, suppliers, purchase orders, channel synchronization, stock overrides, shipment simulation, and operational settings.
- An Operator can read inventory and orders and execute an assigned packing session. An Operator cannot create negative stock, alter product or supplier configuration, advance shipment state manually, or operate another user's active packing session.
- A Manager may explicitly take over or operate any packing session, and the action is recorded.
- Anonymous requests cannot access business APIs or media.

Object-level permission checks are enforced server-side; hiding frontend buttons is only a usability measure. Login endpoints receive rate limiting. Production configuration uses environment-provided secrets, secure cookies, HTTPS redirects, trusted hosts/origins, and non-debug media handling.

### 3.2 Administrative safety

Seeded demonstration accounts are never superusers. Workflow and ledger models are read-only in Django Admin unless an admin action calls the same validated service used by the API. Append-only records cannot be changed or deleted through Admin. Direct status editing for sales orders, packing sessions, shipments, notifications, stock movements, and submitted purchase orders is disabled.

The demo reset command refuses to run unless an explicit disposable-environment setting is enabled. It requires a confirmation flag and only removes records owned by the designated demo dataset. It also clears injected feed fixtures and associated media files. Production data cannot be deleted by `seed_demo --reset`.

### 3.3 Acceptance

- Permission tests cover anonymous, Operator, Manager, owner, non-owner, and Manager-override cases.
- Django deployment checks produce no unresolved security warning for the documented production settings profile.
- The demo manager cannot access unrestricted Django superuser capabilities.
- A reset attempt against a non-disposable environment exits non-zero without modifying data.

## 4. Module 1 — inventory, suppliers, and purchasing

### 4.1 Stock correctness and idempotency

`StockMovement` remains the append-only source of truth and `quantity_on_hand` remains its transactionally maintained cache. Every business operation supplies a unique, nullable idempotency key. Duplicate keys return the existing movement rather than changing stock twice.

Packing completion and purchase-order receipt re-query and lock their authoritative rows using `select_for_update()` before checking status or outstanding quantity. Concurrent requests therefore serialize on PostgreSQL and cannot double-decrement or double-receive stock. Negative stock requires a Manager-only explicit override and a mandatory audit note.

### 4.2 Purchasing snapshots

A purchase-order line preserves the chosen supplier-product relationship, effective lead time, tier quantity, and unit-price snapshot used when the draft was created. Submission calculates the expected date from that preserved effective lead time, not only from the supplier default. Later supplier or tier changes do not rewrite historical POs.

### 4.3 Acceptance

- PostgreSQL concurrency tests prove one stock effect under simultaneous duplicate packing and receipt requests.
- Ledger reconciliation reports zero drift after every lifecycle test.
- Operator negative-stock attempts return 403; approved Manager overrides create an auditable movement.
- A supplier-product lead-time override produces the same expected date in the API, UI, and database.

## 5. Module 2 — multi-channel order aggregation

### 5.1 Source state and internal workflow state

`SalesOrder.status` represents Burk's internal fulfilment state. A separate `source_status` records the latest status reported by Daraz or Burk. Synchronization always updates source metadata and the raw payload, but it cannot rewind a locally controlled order from packing, packed, shipped, or delivered to an earlier state.

An order's fulfilment lines become an immutable packing snapshot once a packing session has started. Later source changes are recorded as reconciliation discrepancies for Manager review; they do not delete or replace lines referenced by scan history. Pending, untouched orders may be refreshed atomically.

### 5.2 Per-record ingestion and reconciliation

Connectors fetch raw records first. Each raw record is normalized and ingested independently, producing an auditable outcome: created, updated, unchanged/duplicate, or failed. `SyncRun.fetched` always equals the number of raw records returned by the source, including malformed records. One malformed record cannot discard valid neighbours.

Queue reconciliation treats connector failures as integrity failures. It requires at least one successfully inspected enabled source and compares external ID, source status, monetary totals, line count, quantities, SKUs, and a canonical payload/line hash. Missing local records, duplicate keys, field mismatches, stale locally retained source records within the configured source window, and unavailable required channels all make the result fail.

The sync API returns a non-successful overall result when any required channel fails. The response exposes per-channel and per-record errors without leaking credentials or secret headers. The frontend shows red failure status and never produces a success-only toast for a partial or failed run.

### 5.3 Connector contract

Every connector supports pagination/cursors, bounded request timeouts, retryable-versus-terminal error classification, clock/window parameters, authentication refresh where required, rate-limit handling, and deterministic idempotency keys. Fixture connectors implement the same normalized contract as live connectors and are only enabled in demo/test environments.

Live completion requires:

- Daraz Open Platform application key, secret, seller access token, API region/base URL, and a sandbox or approved seller account.
- Burk's authoritative order interface contract: REST API, webhook, or database read model; its authentication method; stable order and line identifiers; status mapping; pagination/window semantics; and a staging endpoint or database.

### 5.4 Acceptance

- A two-record feed with one malformed record imports the valid record and reports fetched=2, failed=1.
- A re-sync cannot rewind a packed or shipped order or invalidate historical scan links.
- Source outage, zero inspected required channels, dropped records, duplicated records, or field mismatch makes `check_order_integrity --check` exit non-zero.
- Replaying the same source window creates no duplicate order or line.
- Live Daraz and Burk acceptance requires staged create/update/cancel scenarios and a field-by-field reconciliation report with zero unexplained differences.

## 6. Module 3 — fulfilment and barcode verification

### 6.1 Valid packable orders

An order can start packing only when it has at least one line and every line has a strictly positive integer quantity. Empty orders and zero/negative quantities are rejected at connector normalization, service, and database boundaries where practical.

Manual confirmation is permitted only for a line whose product has no barcode. A line with a configured barcode must be satisfied by successful server-audited scans. A mismatch or overscan never counts as progress.

### 6.2 Session ownership and concurrency

Starting a session assigns its Operator. Only that Operator or a Manager may retrieve, scan, manually confirm, complete, or cancel it. Completing a session locks the fresh session and order rows before checking state. A duplicate or concurrent completion returns the already-completed result without another stock movement, recording, notification, or shipment.

### 6.3 KPI #1 proof

The packing-integrity check requires at least one completed, non-empty session in the measured acceptance window. It verifies positive line quantities, exact successful scan counts, no manual confirmation for barcoded lines, no mismatch attached to a packed line, one stock-decrement effect per stocked line, and a completed session/order state pairing. Zero qualifying sessions cannot produce KPI success.

### 6.4 Acceptance

- Empty and zero-quantity orders cannot start or complete packing.
- A barcoded line's manual-confirm endpoint returns 400.
- A non-owner Operator receives 403 for every session action.
- Simultaneous completion attempts produce one completion and one set of downstream effects.
- `check_pack_integrity --check` fails with zero evidence or any invariant breach and passes with a real successful pack containing an intercepted mismatch.

## 7. Module 4 — packaging surveillance and customer transparency

### 7.1 Capture lifecycle

Recording begins when packing starts and stops only after successful final verification/sealing. The camera adapter exposes explicit start, stop, health, and recover operations. The simulated adapter creates deterministic test clips; the live adapter targets the approved overhead camera or capture service and must survive application-request boundaries.

Compression and customer dispatch are background work, not part of the packing HTTP response. The database records capture start, capture stop, sealing time, processing attempts, sizes, duration, checksums, errors, and final readiness. A failed capture or compression is visible and retryable without changing packing or stock state.

### 7.2 Secure media lifecycle

Raw and compressed objects use unrelated random storage keys. Raw media is never exposed through a customer URL. Authenticated staff media access is authorized against order permissions. Customer access uses short-lived signed links to compressed media. Media is stored outside Django's debug static serving path in production.

A retention policy removes raw footage after successful compression and removes compressed footage after the configured business retention period. Deleting or resetting an eligible demo recording schedules deletion of its physical objects. Cleanup is idempotent and auditable.

### 7.3 KPI #2 proof

The three-minute clock starts at sealing. A qualifying packaging notification succeeds only when every configured required customer channel has a persisted successful send acknowledgement within 180 seconds. Failed, missing, pending, duplicate, zero-recipient, zero-sample, or late delivery makes the KPI fail. The report separates dispatch initiation from provider delivery acknowledgement where the provider supports webhooks.

### 7.4 Acceptance

- A test clip spans packing start through sealing, not merely the post-completion period.
- Compression runs outside the request and can be retried after timeout or process failure.
- Guessing or deriving a raw key from a compressed link fails.
- Media cleanup removes database-eligible files without touching retained records.
- `check_dispatch_latency --check` fails with zero sends or any failed required channel and passes only with non-empty evidence under 180 seconds.
- Live completion requires the approved camera, production media store, signed-link domain, and real channel delivery acknowledgements.

## 8. Module 5 — logistics and courier integration

### 8.1 Shipment contract

Orders retain the structured shipping information required by live carriers: recipient, phone, address lines, city, province, postal code, country, parcel weight/dimensions, item count, declared value, COD amount/payment mode, service type, pickup account, and customer instructions. `Shipment` records the provider booking ID, tracking number, label reference, request idempotency key, and raw redacted response.

Booking is performed by an idempotent background operation after packing commits. Carrier outages create a retryable operational failure rather than silently pretending shipment automation succeeded. A unique idempotency key and provider booking ID prevent duplicate airway bills.

### 8.2 Webhooks and state transitions

Production shipment changes enter through a courier webhook endpoint that verifies provider signatures, stores a unique provider event ID, rejects replay, and maps provider status to allowed forward internal transitions. The authenticated “simulate advance” API is available only in explicitly enabled demo environments and only to Managers.

### 8.3 Acceptance

- Duplicate booking requests produce exactly one provider booking and Shipment.
- Provider timeout/retry and duplicate webhook scenarios preserve one coherent state history.
- An Operator cannot advance shipment state.
- Shipment integrity fails for a completed pack without a successfully booked shipment.
- Live completion requires successful sandbox/production booking, label retrieval, tracking, signed webhook, cancellation/exception handling, and reconciliation for the selected courier.

## 9. Module 6 — post-purchase notifications and reviews

### 9.1 Durable outbox

Notification creation uses a unique business idempotency key composed from order, kind, channel, and triggering event. A database-backed outbox claims due work transactionally with `select_for_update(skip_locked=True)` and a processing lease. Multiple workers cannot send the same attempt concurrently.

Failures store attempt count, error class, next retry time, and terminal state. Retryable failures use bounded exponential backoff. Expired processing leases return to the queue. Provider message IDs and delivery webhooks are persisted and deduplicated. Scheduled review requests are sent by a durable production scheduler; the management command remains a manual operational tool, not the production scheduler itself.

### 9.2 Review destination

Review links are generated by a configured Burk review-link provider using the storefront's real order/customer token or review API contract. Internal `SO-xxxxx` references are not assumed to be public storefront identifiers. The application records notification delivery status; review content itself is stored only if Burk's confirmed scope requires it.

### 9.3 Acceptance

- Parallel workers claim a due notification once.
- Retryable failure eventually succeeds without creating duplicate provider messages.
- Terminal failures and overdue scheduled work make operational checks fail.
- Review links resolve to the approved Burk destination for the intended order without exposing sequential internal IDs.
- Live completion requires SMTP/provider delivery, WhatsApp Business API delivery, webhook acknowledgement, scheduler operation, and a valid Burk review destination.

## 10. Frontend and operator experience

All paginated operational lists either expose pagination controls or deliberately fetch all pages for bounded summaries. Mutation flows display server validation and partial-integration failures. Network failures produce explicit retryable error states rather than false “not found” or success messages.

Role-restricted actions are hidden in the UI and independently forbidden by the API. Clickable table rows are keyboard accessible. Packing retains immediate client feedback but treats the server scan ledger as authoritative. Integration and KPI dashboards show evidence counts, channel health, failed records, retries, and the timestamp/window being measured.

Acceptance requires clean TypeScript, ESLint, production build, keyboard navigation of primary workflows, and browser tests for Manager and Operator lifecycle paths.

## 11. Observability, operations, and deployment

Structured logs include a correlation ID, order reference, sync run, packing session, recording, shipment, and notification attempt without exposing credentials or sensitive payloads. Health checks distinguish application, database, worker, scheduler, storage, and enabled external-adapter health. Metrics cover queue depth, retries, source lag, pack mismatch, dispatch latency, booking failures, and media-processing duration.

Production deployment includes PostgreSQL backups and restore testing, HTTPS, secret management, static/media storage, worker and scheduler processes, process restart policy, database migrations, log retention, monitoring/alerts, and a rollback procedure. CI runs backend tests against PostgreSQL, migration drift checks, integrity acceptance fixtures, frontend type-check/lint/build, and deployment checks.

## 12. Verification and completion reporting

Every implementation subtask follows red-green-refactor testing. Final code-complete verification consists of:

```bash
cd backend
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
uv run python manage.py recalculate_stock --check
uv run python manage.py check_order_integrity --check
uv run python manage.py check_pack_integrity --check
uv run python manage.py check_dispatch_latency --check
uv run python manage.py check_shipment_integrity --check

cd ../frontend
npm run typecheck
npm run lint
npm run build
```

If the frontend package does not yet expose `typecheck`, that script is added as part of implementation and runs `tsc --noEmit`. PostgreSQL—not SQLite—is authoritative for concurrency acceptance. Browser acceptance covers login, authorization boundaries, inventory/reorder/receipt, multi-channel sync success and failure, barcode mismatch and successful pack, recording processing, shipment booking/webhook, review scheduling, and logout.

Completion reports use a requirement matrix with one of four statuses: Verified, Failed, External blocker, or Not started. “100% live-complete” is permitted only when every row is Verified. External blockers do not reduce the truthfulness of code-complete status, but they prevent a live-complete claim.

## 13. Explicit external inputs required for live completion

The following are required from Burk or its authorized providers before the corresponding live gates can run:

- Daraz Open Platform application and seller credentials.
- Burk order, webhook, and review-link API/database contracts plus staging access.
- Selected courier account, API documentation, sandbox credentials, webhook secret, and pickup/service configuration.
- WhatsApp Business sender/provider credentials and approved templates.
- Production email provider credentials and sender-domain authentication.
- Camera model or capture-service interface and access to representative hardware.
- Production object-storage/CDN account and signing configuration.
- Deployment target, domain/DNS, TLS, secret store, worker/scheduler runtime, monitoring, and backup destination.

No credential value is committed to source control. Contract and staging tests use environment-provided secrets and redact sensitive request/response material.
