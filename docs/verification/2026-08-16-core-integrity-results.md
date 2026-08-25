# Core Integrity Gate — Verification Results

**Date:** 2026-08-16  
**Branch:** `codex/production-completion`  
**Scope:** Production-completion Gate 1 (data integrity, concurrency, authorization, and truthful KPI evidence)

## Outcome

Gate 1 passes. The result applies to the local application, PostgreSQL-backed workflows, simulated development connectors, and the automated/browser evidence listed below. It does **not** claim that live Daraz, Burk storefront, courier, WhatsApp, email, or camera integrations are complete; those remain credential/hardware-gated production work.

## Backend regression evidence

Run against PostgreSQL 16 on port 5433:

```bash
cd backend
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
```

Result:

- Django system check: no issues.
- Migration check: no model/migration drift.
- Full suite: **113 tests passed** in approximately 100 seconds.
- PostgreSQL concurrency regressions passed for duplicate pack completion and duplicate PO receipt.

Frontend verification:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Result:

- TypeScript: passed.
- ESLint: passed with no errors or warnings.
- Next.js production build: passed; all 13 application routes generated.

## Isolated acceptance environment

Acceptance used a separate database, `burk_gate1_accept_20260816`, so lifecycle mutations did not alter the normal development database. Migrations and demo seeding completed successfully, producing 9 products, 3 suppliers, and 10 aggregated orders.

One order (`SO-00001`) was exercised through the full local lifecycle:

1. Start a packing session.
2. Scan the required barcode.
3. Complete packing exactly once and decrement stock exactly once.
4. Generate and compress the packaging-video evidence.
5. Record email and WhatsApp dispatches.
6. Automatically book a simulated TCS shipment and record tracking dispatches.

## Integrity/KPI commands

All commands completed with exit code 0 against the isolated acceptance database:

```bash
uv run python manage.py recalculate_stock --check
uv run python manage.py check_order_integrity --check
uv run python manage.py check_pack_integrity --check
uv run python manage.py check_dispatch_latency --check
uv run python manage.py check_shipment_integrity --check
```

Observed evidence:

- Stock ledger: 9 products checked, zero drift.
- Multi-channel aggregation: 0 dropped, 0 duplicated, 10 unique records; no stale or mismatched canonical records.
- Barcode verification: 1 qualifying completed pack and 1 accepted scan; no empty or invalid completed sessions.
- Packaging communication latency: 2 sent notifications, maximum 0.4 seconds, zero failed/overdue/breached notifications.
- Shipment tracking: 2 sent notifications and 1 automatic shipment, with no integrity breach.

## Authenticated browser acceptance

The production Next.js build was tested through `http://localhost:3001` with Django on the isolated acceptance database.

Manager checks:

- Login succeeded and the dashboard rendered 9 SKUs, 4 low-stock products, 1 out-of-stock product, and 0 open purchase orders.
- Orders page showed **0 dropped · 0 stale · 0 duplicated · 0 mismatched · 10 unique**.
- “Sync now” completed and visibly reported 0 new / 10 updated; the canonical integrity banner remained green.
- `SO-00001` preserved internal status `Shipped` while separately displaying channel-reported status `Pending`.
- Order detail showed the immutable line snapshot, simulated TCS booking, packaging-video dispatches, and shipment-tracking dispatches.
- Packing detail showed `Packed`, video ready, both video notifications sent within 0.4 seconds, and shipment booked.
- The generated compressed clip was fetched through the production Next.js `/media/` proxy with HTTP 200, `video/mp4`, and the expected 35,321-byte payload.

Operator checks:

- Operator login succeeded.
- Manager-only Suppliers and Purchase Orders navigation was absent.
- API regression tests independently confirmed that an operator cannot retrieve, scan, manually confirm, complete, cancel, or claim another operator's active packing session.

Browser console check: no warning or error entries were recorded during acceptance.

## Gate 1 fixes covered

- Empty/non-positive orders cannot pass packing validation.
- Barcoded lines cannot bypass scanning through manual confirmation.
- KPI #1 and #2 commands fail when qualifying evidence is absent.
- Packing-session ownership is enforced server-side.
- Pack completion and PO receipt lock authoritative PostgreSQL rows and are retry-safe.
- Purchase-order lines preserve supplier-product, tier, price, and lead-time snapshots.
- Channel-reported order status is separated from internal fulfilment status.
- A resync cannot rewind a locally packed order or replace its immutable packed line snapshot.
- Malformed source records are counted individually without discarding valid neighbours.
- Sync API/UI distinguishes complete, partial, and failed synchronization.
- Multi-channel reconciliation checks missing, duplicate, stale, status, total, item-count, and line-level discrepancies.

## Remaining production gates

Gate 1 is not the whole production-completion program. Remaining gates include production security/configuration, background-job reliability, observability/backups, deployment packaging, and real connector/courier/messaging/camera acceptance. Live external acceptance requires credentials, webhook/API contracts, approved sender accounts, and physical camera/scanner access supplied by the deployment owner.
