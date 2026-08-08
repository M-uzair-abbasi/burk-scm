# Module 3 — Intelligent Fulfilment & Barcode Verification (Design Spec)

**Date:** 2026-07-30
**Status:** Approved, in build
**Module:** 3 of 7 (Burk.pk SCM-OVS)
**Estimate line items:** Connect barcode scanner · Packing list + scan matching · Error alert (flash + sound) · Testing

## 1. Goal & KPI

The **packing station**: an operator picks an order from the Module 2 queue, works a
digital packing list, and **scans each item's barcode** before sealing it. If a scanned
item does not belong to the active order, the interface **instantly flashes a large red
warning and emits an audio alert** to block the wrong item. When every item is verified,
the pack completes: stock is decremented and the order moves to **Packed**.

This module owns:

> **KPI #1 — Zero-Mismatch Validation:** the barcode mechanism must intercept and
> visually/audibly flag **100% of mismatched items** scanned during test packaging loops.

## 2. Scanner reality (no fake hardware layer)

Physical barcode/QR scanners are **keyboard-wedge** devices: they "type" the decoded
string followed by Enter into the focused field. So one autofocused scan input serves a
**real scanner, manual typing, and a "Simulate scan" button** identically. Nothing to
mock — plug a real scanner into the Burk.pk station and it works unchanged.

## 3. Validation architecture (decided: hybrid)

- The station loads the order's **expected barcodes** with the packing list, so a scan
  **flashes/beeps instantly** with no round-trip.
- **Every** scan is also POSTed to an **append-only `PackScan` server log** that
  independently re-validates. Real-time feedback + a tamper-proof audit trail = the
  strongest KPI-1 evidence.
- Pack-complete is **server-verified** (all lines fully scanned) before any stock moves.

## 4. Boundary with other modules

- Consumes the Module 2 order queue (orders in `pending`/`confirmed`). Does not re-open
  Module 2 ingestion.
- **This is where stock finally moves** (the boundary Module 2 deferred): completion posts
  `SALE` movements through `inventory.services.record_movement`.
- Module 3 ends at **Packed + stock decremented**. Courier booking / airway bill /
  tracking is **Module 5**.

## 5. Data model — new `fulfillment/` app

Two new models; reuses `SalesOrder`, `SalesOrderLine`, `Product`, `StockMovement`.

### 5.1 `PackingSession`
One packing attempt for an order.

| Field | Type | Notes |
|---|---|---|
| `order` | FK → orders.SalesOrder, PROTECT, related_name `packing_sessions` | |
| `status` | choices `in_progress` / `completed` / `cancelled` | |
| `operator` | FK → user, PROTECT, null | who packs |
| `started_at` | DateTime auto_now_add | |
| `completed_at` | DateTime null | |

Constraint: **partial `UniqueConstraint(order)` where `status='in_progress'`** — at most
one active session per order.

### 5.2 `PackScan` — append-only scan ledger (KPI-1 proof)
One row per scan, **including rejected ones** — that is what proves 100% interception.

| Field | Type | Notes |
|---|---|---|
| `session` | FK → PackingSession, CASCADE, related_name `scans` | |
| `barcode` | CharField | raw scanned string (blank for manual confirm) |
| `line` | FK → orders.SalesOrderLine, SET_NULL, null | matched line, null on mismatch |
| `product` | FK → inventory.Product, SET_NULL, null | matched product, null on mismatch |
| `result` | choices `ok` / `mismatch` / `overscan` | |
| `manual` | bool default False | true for barcodeless manual confirm |
| `operator` | FK → user, PROTECT, null | |
| `scanned_at` | DateTime auto_now_add | |

Save-guarded against edits (append-only, like `StockMovement`/`SyncRun`). Line progress is
**computed** from `ok` scans (`scanned_qty = count of ok PackScans for that line`); no
denormalized cache at this scale.

## 6. Validation service — `fulfillment/services.py`

- `start_packing(order, *, user)` — guards `order.status` ∈ {pending, confirmed}; returns
  the in-progress session (idempotent: returns the existing active one).
- `record_scan(session, barcode, *, user)` — resolves `barcode` → `Product` → an order
  line that still needs that product. Result:
  - **`ok`** — product is on an order line whose scanned_qty < quantity; attach line+product.
  - **`overscan`** — product is on the order but that line's quantity is already met.
  - **`mismatch`** — unknown barcode, or a product not on this order.
  Appends a `PackScan` **always** (even mismatch/overscan); returns it + fresh progress.
- `confirm_line_manual(session, line, *, user)` — records an `ok` `PackScan(manual=True)`
  for a line whose product has no barcode (or is unstocked); guarded to not exceed quantity.
- `complete_packing(session, *, user)` — refuses (ValidationError) unless every line is
  fully scanned; then in one `@transaction.atomic`: `record_movement(reason=SALE,
  quantity_delta=-qty)` per stocked line (the oversell guard blocks shipping more than on
  hand), set `order.status='packed'`, `session.status='completed'`.
- `session_progress(session)` — per-line `{required, scanned, complete}` + overall flag.
- `cancel_packing(session)` — sets `cancelled`.

**`check_pack_integrity` management command** (KPI-1 analog of `check_order_integrity`):
asserts no `completed` session has an unfinished line, and no `mismatch`/`overscan` scan is
counted as progress. `--check` exits non-zero on any breach.

## 7. API — `fulfillment/` (DRF)

- `GET /api/packing/queue/` — orders awaiting packing (status pending/confirmed, no
  completed session), prioritised by `placed_at` ascending ("receipt time").
- `POST /api/packing/` `{order}` → start; returns session detail.
- `GET /api/packing/{id}/` → session with lines (each: sku, product_name, **barcode**,
  required_qty, scanned_qty, complete), progress, recent scans.
- `POST /api/packing/{id}/scan/` `{barcode}` → `{result, line, progress}`.
- `POST /api/packing/{id}/confirm_line/` `{line}` · `POST .../complete/` · `POST .../cancel/`.
- `IsAuthenticated` — operators run the floor.

## 8. Frontend — new **Packing** nav (all authenticated users)

- `/packing` — pack queue: orders awaiting packing (prioritised), each with **Start packing**.
- `/packing/[id]` — the **packing station**:
  - a big **autofocused scan input** (keyboard-wedge scanner / typing / **Simulate scan**),
  - a live **checklist**: each line fills green as its barcode is scanned the required
    number of times; barcodeless lines show a manual **Confirm** button,
  - **mismatch → full-width red flash overlay + Web Audio buzz** (self-contained, no asset
    files) that blocks the item; match → soft tick,
  - a **scan-history** strip (ok / mismatch),
  - **Complete pack** button, enabled only when all lines are done → order Packed, stock
    dropped, back to queue.
- Reuses `lib/api.ts`, `lib/format.ts`, the `(app)` shell, and the badge patterns.

## 9. Seed & demo

- The Module 2 feeds already yield packable orders with **barcoded, stocked** products
  (e.g. BRK-ORD-10001 → Oxford Shirt M, BRK-ORD-10002 → Cotton Kurta M + Leather Belt,
  daraz 700100003 → Cotton Kurta M). `seed_demo --reset` also clears `PackScan` /
  `PackingSession` (before Products, respecting FKs).

## 10. Tests — `fulfillment/tests.py` (proves KPI #1)

- Matched scan → `ok`, line progresses; unknown barcode → `mismatch`, no progress; product
  not in order → `mismatch`; overscan → `overscan`, no extra progress.
- **100%-interception batch:** a mixed stream of valid + invalid scans → every invalid one
  is flagged and none counts toward completion.
- Manual confirm for a barcodeless line.
- Complete refuses while any line is unfinished.
- Complete decrements stock (ledger balance drops by ordered qty) and sets order → Packed,
  session → completed.
- Oversell guard: completing an order exceeding on-hand raises, nothing half-applied.
- `PackScan` is append-only (edit raises); `check_pack_integrity` clean after a full pack.

## 11. How to verify Module 3 is complete

1. `uv run python manage.py test fulfillment` → green.
2. `uv run python manage.py check_pack_integrity` → clean.
3. full regression suite green; `recalculate_stock --check` still consistent.
4. `npm run build` → `/packing` routes compile.
5. Live browser demo: pick an order → scan its items (lines go green) → scan a **wrong
   barcode → red flash + beep, blocked** → complete → order flips to **Packed** and stock
   drops in the ledger.

## 12. Subtask record (built one at a time, verified each)

1. **M3-MODELS** — app + `PackingSession` + append-only `PackScan` + migration + admin.
2. **M3-SERVICE** — start/scan/confirm/complete + SALE decrement + `check_pack_integrity`.
3. **M3-TESTS** — suite proving KPI #1 + stock decrement, run green.
4. **M3-API** — serializers, packing viewset (queue/start/scan/confirm/complete/cancel), HTTP smoke.
5. **M3-SEED** — packable demo orders + fulfillment reset in `seed_demo`.
6. **M3-FE-QUEUE** — Packing nav + pack-queue page.
7. **M3-FE-STATION** — packing station: scan input, checklist, red flash + audio, complete.
8. **M3-VERIFY** — tests + integrity + build + live browser demo; update README & memory.
