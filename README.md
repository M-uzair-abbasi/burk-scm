# Burk.pk SCM-OVS

**Automated Supply Chain & Smart Order Verification System** — an industrial-internship FYP for Burk.pk (Devomech Solutions).

The system digitises Burk.pk's warehouse: it aggregates orders across channels, verifies packing with barcode hardware, records packing on video, books couriers, and messages customers. It is built **one module at a time**, each fully finished and verified before the next begins.

## What's in this repo right now

**Module 0 (Setup & Foundations)** and **Module 1 (Inventory & Suppliers)** are complete:

- Custom user model with `manager` / `operator` roles and session auth.
- Inventory with an **append-only stock ledger** + a denormalised `quantity_on_hand` cache (both written in one transaction, provably consistent).
- Low-stock alerts computed on read.
- Suppliers with wholesale price tiers and a database-guaranteed single preferred supplier per product.
- Purchase orders: reorder-from-product → submit → receive-into-stock, all through the ledger.
- A Next.js warehouse console: login, dashboard, inventory, product detail with live stock adjustment, suppliers, and purchase orders.

**Module 2 (Multi-Channel Order Aggregation)** is complete:

- Customer orders pulled from **Burk.pk and Daraz.pk** into one unified, de-duplicated queue.
- A pluggable **channel-connector** interface with simulated Burk/Daraz feeds (deliberately different shapes, normalised to one model); a real Daraz Seller Center client is a documented drop-in (`orders/connectors/live_daraz.py`).
- **Idempotent ingestion** keyed on `(channel, external_id)` with an append-only **`SyncRun`** reconciliation ledger — every sync satisfies `fetched == created + updated + duplicates_skipped + failed`, so **no record is dropped or duplicated** (project KPI #3).
- An **Orders** console screen: unified queue, channel/status filters, search, a **Sync now** button, and a live `0 dropped · 0 duplicated · N unique` integrity badge; plus an order-detail view with product-resolved lines and the raw channel payload.

**Module 3 (Intelligent Fulfilment & Barcode Verification)** is complete:

- A **packing station**: pick an order from the queue, work a digital packing list, and **scan each item's barcode** before sealing.
- **Real-time mismatch interception** — scanning an item that doesn't belong to the order flashes a full-screen red warning and sounds an audio buzz to block it (project KPI #1). Every scan, matched or not, is written to an append-only **`PackScan`** ledger, so 100% interception is auditable (`check_pack_integrity`).
- Keyboard-wedge friendly: the scan input works with a real barcode/QR scanner, manual typing, or the on-screen simulate buttons — identically.
- Completing a pack decrements stock through the ledger (`SALE` movements) and marks the order **Packed** — this is where Module 2's deferred stock movement finally happens.

**Module 4 (Automated Video Surveillance & Customer Transparency)** is complete:

- The moment a pack is completed, the system **records the packaging sequence**
  (an overhead-camera adapter — simulated here via ffmpeg since no physical
  camera is wired into this dev environment, a real RTSP/USB feed is a
  documented drop-in), **compresses it with ffmpeg** (a genuine re-encode, not a
  copy — the clip really does shrink), and **emails + WhatsApps** it to the
  customer, all before the "Complete pack" response returns.
- A shared, append-only **`Notification`** ledger (also used by Modules 5 and 6)
  records every dispatch attempt with its channel, status, and latency —
  `sent_at - reference_event_at` is the literal KPI #2 number.
  `check_dispatch_latency` proves every packaging-video notification initiated
  within **3 minutes** of the order being sealed.
- Email goes through Django's real mail backend (console in dev, one env var
  away from real SMTP/SendGrid). WhatsApp has no real credentials available in
  this environment, so it's a simulated Cloud-API-shaped adapter; a real
  integration is a documented drop-in (`notifications/channels/live_whatsapp.py`).

**Module 5 (Logistics Integration & Automated Tracking)** is complete:

- **Instant Airway Bill Booking** — the moment a pack completes (right after
  Module 4's video dispatch), a courier (Leopard / TCS / Trax / M&P, rotated
  deterministically) is booked automatically and the order flips to **Shipped**.
  No manual data entry.
- The resulting tracking number is **emailed + WhatsApped** to the customer
  through the same Notification ledger, and every status change — booked, in
  transit, delivered — is written to an append-only **`ShipmentEvent`** log
  (`Shipment.status` is a cache of the latest event, the same ledger-plus-cache
  shape as the stock ledger). `check_shipment_integrity` proves booking never
  has a manual gap.
- No real courier credentials exist here, so booking is simulated (shaped like
  a real courier API response); a real Leopard integration is a documented
  drop-in (`logistics/couriers/live_leopard.py`). A courier's delivery webhook
  is simulated with `simulate_delivery_update` (mirrors `simulate_new_order`).

**Module 6 (Post-Purchase Engagement Loop)** is complete:

- The instant a shipment is marked **Delivered**, a review-request notification
  is **scheduled** (not sent immediately — a real deployment reminds customers
  hours/days later, not the second the parcel arrives) through the same
  Notification ledger, `scheduled_for` = delivered time + `REVIEW_REMINDER_DELAY_SECONDS`.
- `dispatch_scheduled_notifications` is the sweep that sends anything now due —
  standing in for a cron/Celery-beat tick, the same "manual trigger acts as the
  scheduler" pattern `sync_orders` already uses for channel polling.

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5.2 LTS + Django REST Framework |
| Database | PostgreSQL 16 (Docker) |
| Frontend | Next.js 16 + React 19 + Tailwind v4 |
| Python deps | [uv](https://docs.astral.sh/uv/) + `pyproject.toml` |
| Auth | Django session auth (no JWT) |

## Prerequisites

- **Docker** + Docker Compose
- **uv** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 20+** and npm
- **ffmpeg** on `PATH` (Module 4 packaging-video capture/compression shells out to it — `sudo apt install ffmpeg` or equivalent)

## Quick start (≈10 minutes from a clean clone)

### 0. Two environment gotchas (read these first)

- **Docker permissions.** If `docker ps` fails with a permission error, add yourself to the docker group **and log out and back in fully** (a new terminal is not enough):
  ```bash
  sudo usermod -aG docker $USER
  ```
  If you can't re-login right now, prefix every docker command with `sudo` instead.
- **Port 5433, not 5432.** Postgres is mapped to host port **5433** on purpose — 5432 is commonly taken by another local Postgres. The `DATABASE_URL` already points at 5433.

### 1. Configure environment

```bash
cp .env.example .env      # dev defaults already work as-is
```

### 2. Start Postgres

```bash
docker compose up -d
docker compose ps         # wait until the db service is "healthy"
```

### 3. Backend

```bash
cd backend
uv run python manage.py migrate
uv run python manage.py seed_demo      # demo users, products, suppliers, stock
uv run python manage.py runserver 127.0.0.1:8000
```

### 4. Frontend (new terminal)

```bash
cd frontend
npm install
npm run dev               # http://localhost:3001
```

### 5. Log in

Open **http://localhost:3001** and sign in:

| User | Password | Sees |
|---|---|---|
| `manager` | `burkdemo123` | Everything, including supplier & PO actions |
| `operator` | `burkdemo123` | Inventory only; can record stock movements, cannot reorder |

## The demo loop

1. **Dashboard** shows total SKUs, low-stock, out-of-stock, and open-PO counts, plus a low-stock panel.
2. Open a healthy product → **Adjust stock** below its safety level → it turns **Low** and appears on the dashboard (alert fires live).
3. On a low-stock product, click **Reorder** → the modal preselects the preferred supplier, shows the tier price and lead time → **Create draft PO**.
4. **Purchase Orders** → **Submit** (stamps expected date = today + lead time) → **Receive** (stock rises, the product drops off the low-stock panel).
5. Back on the product, the **movement ledger** shows the purchase receipt, and `SUM(deltas)` equals the on-hand number.

### Order aggregation (Module 2)

1. **Orders** shows the unified Burk + Daraz queue with a green `0 dropped · 0 duplicated · 10 unique` integrity badge.
2. Click **Sync now** repeatedly — the counts stay stable and the badge stays `0/0`: re-syncing an order updates it, it never creates a duplicate.
3. Inject a fresh order, then pull it in:
   ```bash
   cd backend
   uv run python manage.py simulate_new_order --channel daraz
   ```
   Click **Sync now** again → the new order appears **exactly once** and the unique count rises by one.
4. Open any order to see product-resolved lines (an unstocked marketplace SKU is flagged) and the raw channel payload.

### Barcode verification (Module 3)

1. **Packing** lists orders awaiting packing, oldest first. Click **Start packing** on one.
2. At the station, scan (or type + Enter) each item's barcode — the line fills green as its
   required quantity is verified.
3. Scan an item that doesn't belong to the order → a **full-screen red flash + audio buzz**
   blocks it; the mismatch is logged but never counts toward completion.
4. Once every item is verified, click **Complete pack** → stock is decremented (a `SALE`
   ledger movement per line) and the order flips to **Packed**.

### Video, shipping & the review reminder (Modules 4–6)

Completing a pack (previous step) automatically chains the rest of the order
lifecycle — nothing further to click for video + shipping:

1. Right after **Complete pack**, the station shows a **Customer transparency**
   panel: a short compressed video, and Email/WhatsApp dispatch confirmation
   with the exact latency each channel took (well under the 3-minute KPI).
2. It also shows a **Shipment** panel: courier, tracking number, and a
   **Simulate: mark in transit / mark delivered** button pair (there's no real
   courier webhook in this environment, so this stands in for one). The same
   panel — plus the full notification history — is on the order's own detail
   page (**Orders** → open an order).
3. Click **Simulate: mark delivered** → the order flips to **Delivered** and a
   review-request notification is **scheduled** (not sent instantly — see it
   listed as "Scheduled" in Customer notifications). Run:
   ```bash
   cd backend
   uv run python manage.py dispatch_scheduled_notifications
   ```
   Before the delay elapses it reports "No due notifications" (proving it does
   **not** fire early); after `REVIEW_REMINDER_DELAY_SECONDS` (60s by default)
   run it again and the reminder sends — refresh the order page to see it flip
   to "Sent".

## Useful commands

```bash
cd backend
uv run python manage.py test                        # full test suite
uv run python manage.py recalculate_stock --check    # prove ledger == cache (exits non-zero on drift)
uv run python manage.py check_order_integrity        # prove no dropped/duplicated orders — KPI #3 (exits non-zero on drift)
uv run python manage.py check_pack_integrity         # prove no mismatch was ever packed — KPI #1 (exits non-zero on breach)
uv run python manage.py check_dispatch_latency       # prove every video dispatched within 3 min — KPI #2 (exits non-zero on breach)
uv run python manage.py check_shipment_integrity     # prove courier booking is never a manual gap
uv run python manage.py sync_orders                  # pull channel feeds into the queue (CLI "Sync now")
uv run python manage.py simulate_new_order --channel daraz     # inject one demo order for the next sync
uv run python manage.py simulate_delivery_update SO-00001 --status delivered   # simulate a courier webhook
uv run python manage.py dispatch_scheduled_notifications        # send any due review reminders (cron stand-in)
uv run python manage.py seed_demo --reset            # wipe and reseed demo data (runs an initial order sync)
```

## How it fits together

- The frontend reaches the API through a **Next rewrites proxy** (`/api/*` → `127.0.0.1:8000`), so the browser only ever sees one origin — no CORS, and the session cookie is sent normally. CSRF is still enforced (`CSRF_TRUSTED_ORIGINS` covers `localhost:3001`).
- Every stock change goes through `inventory.services.record_movement()` — one writer, one transaction, row-locked. The ledger is the source of truth; `quantity_on_hand` is a cache of it.
- Order ingestion goes through `orders.services.ingest_channel()` — idempotent on `(channel, external_id)`, one `SyncRun` per channel per sync. The unique constraint guarantees no duplicates; the reconciliation invariant guarantees nothing fetched is dropped. Order ingestion does **not** touch stock — that happens later at fulfilment (Module 3).
- Barcode verification goes through `fulfillment.services` — every scan is appended to the `PackScan` ledger (matched, mismatch, or overscan), and only a `complete_packing` with all lines fully scanned decrements stock (`SALE` movements) and marks the order Packed. A mismatch is recorded but can never advance the pack, which is what makes KPI #1 auditable.
- Completion is the trigger for everything downstream: `fulfillment.views.PackingViewSet.complete()` calls `complete_packing()`, then `surveillance.services.capture_and_dispatch()` (Module 4), then `logistics.services.book_shipment()` (Module 5) — each wrapped so a camera/ffmpeg/courier/notification failure degrades to a `FAILED` status row rather than ever failing the pack response the operator is waiting on. `fulfillment` itself has no dependency on `surveillance`/`logistics` — they're composed at this one call site, not baked into Module 3's own service layer.
- `notifications.services.dispatch()` is the single writer behind every customer-facing send (packaging video, tracking code, review reminder) — one shared, append-only `Notification` ledger with a `channel` adapter registry (mirrors the order-connector pattern). `sent_at - reference_event_at` on each row is the literal KPI #2 number; `check_dispatch_latency` audits it. A notification can also be created with `scheduled_for` in the future (Module 6's review reminder) and picked up later by `dispatch_scheduled_notifications` — a manual "cron tick" management command, the same stand-in role `sync_orders` plays for a real channel poller.
- A courier delivery update — real webhook in production, `simulate_delivery_update` here — goes through `logistics.services.advance_shipment()`, which appends a `ShipmentEvent` and, on `DELIVERED`, both flips the order and schedules Module 6's review reminder. There is no dedicated "Module 6" app: it's this one trigger plus the shared notification scheduler.

## Project layout

```
burk-scm/
├── docker-compose.yml         # postgres:16 on host port 5433
├── .env.example
├── backend/                   # Django + DRF
│   ├── config/                # settings, urls
│   ├── accounts/              # custom User + roles + auth API
│   ├── inventory/             # Category, Product, StockMovement, services, API
│   ├── suppliers/             # Supplier, SupplierProduct, price tiers, API
│   ├── purchasing/            # PurchaseOrder + lines, reorder/submit/receive
│   ├── orders/                # SalesOrder queue, channel connectors, idempotent sync + reconciliation
│   ├── fulfillment/           # PackingSession + append-only PackScan, scan validation
│   ├── surveillance/          # Module 4: packaging-video capture (ffmpeg) + compression
│   ├── logistics/             # Module 5: courier booking, append-only ShipmentEvent log; Module 6's delivery trigger
│   └── notifications/         # Shared append-only Notification ledger + Email/WhatsApp channel adapters (Modules 4-6)
└── frontend/                  # Next.js console (login, dashboard, orders, packing, inventory, suppliers, POs)
```
