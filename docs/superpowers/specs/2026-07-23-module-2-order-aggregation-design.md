# Module 2 — Multi-Channel Order Aggregation (Design Spec)

**Date:** 2026-07-23
**Status:** Approved, in build
**Module:** 2 of 7 (Burk.pk SCM-OVS)
**Estimate line items:** Pull orders from Burk.pk · Connect Daraz API + fetch orders · Merge into one queue (no duplicates) · Order queue screen

## 1. Goal & KPI

Aggregate customer orders from **two sales channels — Burk.pk and Daraz.pk — into one
combined, live, de-duplicated queue.**

This module owns the project's highest-stakes KPI:

> **KPI #3 — Multi-Channel Sync Accuracy:** API loops fetching multi-platform data from
> both Burk.pk and Daraz.pk must reconcile order metrics **without any record dropped or
> duplicated.**

Everything below is organised so that "zero dropped, zero duplicated" is not a claim but
an **auditable, testable invariant**.

## 2. Channel strategy (decided)

We have no live Daraz Seller Center credentials or Burk.pk storefront backend in this
environment. Decision: **pluggable adapter interface + simulated feeds.**

- A `ChannelConnector` interface with two implementations (`BurkConnector`,
  `DarazConnector`) that read **deliberately different-shaped** simulated order feeds.
- The dedup / reconciliation engine behind the connectors is **100% real** and fully
  demoable offline.
- A real Daraz Seller Center API client (`live_daraz.py`) is a documented drop-in that
  replaces the simulated connector **without touching the ingestion core**.

Rationale: the engineering value (and the KPI) is the idempotent, reconciled dedup
engine — not credentials we cannot hold here.

## 3. Boundary with other modules

- Module 2 ingests orders **read-only into the queue**. It does **not** move inventory
  stock. Stock decrements happen later at fulfilment/dispatch (Module 3), when an
  operator packs and seals the order.
- `SalesOrder` is the customer-order model the Module 1 code deliberately reserved the
  `Order` name for (`purchasing.PurchaseOrder` is the supply-side order).

## 4. Data model — new `orders/` app

Three models, mirroring Module 1's append-only-ledger philosophy.

### 4.1 `SalesOrder`
One customer order pulled from a channel.

| Field | Type | Notes |
|---|---|---|
| `channel` | choices `BURK` / `DARAZ` | part of the dedup key |
| `external_id` | CharField | the channel's own order id |
| `reference` | CharField unique | internal `SO-00001`, derived from pk post-insert (like PO numbers) |
| `status` | choices | normalized: PENDING/CONFIRMED/PACKED/SHIPPED/DELIVERED/CANCELLED/RETURNED |
| `customer_name`, `customer_phone`, `customer_email` | Char | denormalized from payload |
| `shipping_address` | Text | denormalized |
| `currency` | Char default `PKR` | |
| `subtotal`, `shipping_fee`, `total` | Decimal(12,2) | money as Decimal |
| `item_count` | PositiveInt | denormalized count of lines |
| `placed_at` | DateTime | when the customer placed it on the channel (from payload) |
| `ingested_at` | DateTime auto_now_add | first time we pulled it |
| `last_synced_at` | DateTime | updated each sync we re-saw it |
| `updated_at` | DateTime auto_now | |
| `raw_payload` | JSONField | snapshot of the source record for audit/repro |

**`UniqueConstraint(channel, external_id)`** — the database-level guarantee of *no
duplicates*. This is the KPI's backbone (the same way the append-only `StockMovement`
ledger backed Module 1's stock integrity).

### 4.2 `SalesOrderLine`
| Field | Type | Notes |
|---|---|---|
| `order` | FK → SalesOrder, related_name `lines`, CASCADE | |
| `sku` | CharField | as received from the channel |
| `product` | FK → inventory.Product, null=True, SET_NULL | soft-matched by SKU at ingest; a marketplace order can reference a SKU we don't stock |
| `product_name` | CharField | snapshot from payload |
| `quantity` | PositiveInt | |
| `unit_price`, `line_total` | Decimal(12,2) | |

### 4.3 `SyncRun` — append-only reconciliation ledger
One row **per channel per sync invocation**. The proof artifact for KPI #3.

| Field | Type | Notes |
|---|---|---|
| `channel` | choices | which channel this run pulled |
| `started_at`, `finished_at` | DateTime | |
| `fetched` | int | records the connector returned |
| `created` | int | new orders inserted |
| `updated` | int | existing orders refreshed |
| `duplicates_skipped` | int | intra-batch repeats of an already-seen key |
| `failed` | int | records that errored during ingest |
| `ok` | bool | |
| `detail` | JSONField | per-record notes / error messages |

**Enforced invariant:** `fetched == created + updated + duplicates_skipped + failed`.
Combined with the unique constraint (nothing duplicated), this pair *is* KPI #3, made
auditable. `SyncRun` is append-only (save guard, like `StockMovement`).

## 5. Connectors — `orders/connectors/`

- `base.py` — `ChannelConnector` ABC: `channel` attribute + `fetch() -> list[dict]`
  (raw source records) + `normalize(raw) -> NormalizedOrder` (a dataclass with a flat,
  channel-agnostic shape). A single `fetch_normalized()` helper wraps both.
- `burk.py` — `BurkConnector`: reads a Burk-shaped simulated feed (snake_case,
  `order_ref`, nested `items`).
- `daraz.py` — `DarazConnector`: reads a Daraz-shaped simulated feed (different:
  `order_id`, `order_number`, `paid_price`, `address_shipping`, `order_items`). The
  different shape makes normalization real work, not a pass-through.
- Feeds live as fixtures/generators and include an **intentional intra-batch duplicate**
  to exercise dedup, plus a way to inject a brand-new order live (for the demo).
- `live_daraz.py` — documented stub showing where the real Seller Center client lands.

## 6. Ingestion service — `orders/services.py`

Mirrors `inventory.services.record_movement` discipline: one writer, transactional,
idempotent.

- `ingest_channel(channel, *, user=None) -> SyncRun`:
  1. calls the connector's `fetch_normalized()`,
  2. for each record, **idempotent upsert** keyed on `(channel, external_id)` inside
     `@transaction.atomic` (`update_or_create`); re-syncing an order updates it, never
     creates a second row,
  3. resolves `product` by SKU, rebuilds the order's lines,
  4. tallies created/updated/duplicates_skipped/failed and writes one `SyncRun`.
- `sync_all(*, user=None) -> list[SyncRun]`: runs every channel connector.
- Concurrency-safe: the DB unique constraint turns a racing double-insert into an
  `IntegrityError` that is caught and treated as "already exists".

Also a management command **`check_order_integrity`** (the KPI-3 analog of
`recalculate_stock --check`): reports `dropped` (fetched-but-missing) and `duplicated`
(same key twice in the queue — impossible under the constraint, verified anyway) and the
unique-order total; `--check` exits non-zero on any drift for CI.

## 7. API — `orders/` (DRF, matching Module 1)

- `SalesOrderViewSet` — read-only `list` (filter by `channel`, `status`; search
  `external_id` / `reference` / `customer_name`) + `retrieve` (with lines).
- `POST /api/orders/sync/` — the **"Sync now"** trigger. `IsAuthenticated` (operators run
  the warehouse floor). Returns the `SyncRun` summaries.
- `GET /api/orders/summary/` — per-channel and per-status counts, last sync time per
  channel, and the live **integrity block** (`dropped: 0, duplicated: 0, unique: N`).
- Wired under `/api/` in `config/urls.py` alongside the other apps.

## 8. Frontend — new **Orders** nav (all authenticated users)

- `/orders` — unified queue across both channels: channel badge, `reference`, external
  id, customer, item count, total, status pill, placed/ingested time. Filters (channel,
  status) + search. A prominent **"Sync now"** button that calls the sync action and
  toasts the run summary. A top **reconciliation strip**: per-channel counts, last sync,
  and a green `0 dropped · 0 duplicated · N unique` integrity badge — the KPI made
  visible.
- `/orders/[id]` — order detail: customer + address, lines (with product links where
  matched), totals, collapsible raw payload, and this order's sync history.
- Reuses `lib/api.ts`, `lib/format.ts`, `StockStatusPill`-style pill patterns, and the
  `(app)` auth-guarded shell from Module 1.

## 9. Seed & demo

- Simulated feeds ship as fixtures. `seed_demo` runs an **initial `sync_all()`** so the
  queue is populated on first load; `seed_demo --reset` also clears
  `SalesOrderLine` / `SalesOrder` / `SyncRun` (before Products, respecting FKs).
- A `simulate_new_order` command injects a fresh channel order so a **live demo** shows
  the queue grow by exactly one on the next "Sync now".

## 10. Tests — `orders/tests.py` (this is where KPI #3 is proven)

- Idempotency: ingest twice → same order count; second run is all-updates, 0 created.
- Intra-batch dedup: a feed with a repeated `external_id` → 1 order,
  `duplicates_skipped == 1`.
- DB constraint: manual double-insert of the same `(channel, external_id)` raises
  `IntegrityError`.
- Reconciliation invariant: `fetched == created + updated + duplicates_skipped + failed`
  for every run.
- No-drop: every fetched `external_id` is present in the queue after sync.
- Normalization: Burk-shaped and Daraz-shaped payloads both land with correct fields.
- Product resolution by SKU: matched and unmatched cases.
- Cross-channel key: same `external_id` under `BURK` vs `DARAZ` are two distinct orders.
- `sync_all` returns one run per channel.

## 11. How to verify Module 2 is complete (same rigor as Module 1)

1. `uv run python manage.py test orders` → green.
2. `uv run python manage.py check_order_integrity` → `0 dropped, 0 duplicated, N unique`.
3. `npm run build` → new `/orders` routes compile.
4. Live browser loop: queue shows unified Burk+Daraz orders → click **Sync now**
   repeatedly, counts stay stable and the integrity badge stays `0/0` → inject a new
   order via `simulate_new_order` → next sync shows it appear exactly once.

## 12. Subtask record (built one at a time, verified each)

1. **M2-MODELS** — app + 3 models + migration + admin.
2. **M2-CONNECTORS** — base interface + Burk/Daraz simulated connectors + fixtures.
3. **M2-INGEST** — idempotent ingestion service + reconciliation + `check_order_integrity`.
4. **M2-TESTS** — orders suite proving KPI #3, run green.
5. **M2-API** — serializers, viewset, sync + summary endpoints, urls, HTTP smoke.
6. **M2-SEED** — fixtures + initial sync into `seed_demo`, reset handling, `simulate_new_order`.
7. **M2-FE-QUEUE** — Orders nav + unified queue page.
8. **M2-FE-DETAIL** — order detail page.
9. **M2-VERIFY** — tests + integrity command + build + live browser demo; update README & memory.
