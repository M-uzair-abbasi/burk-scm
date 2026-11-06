# Burk.pk SCM-OVS

**Automated Supply Chain & Smart Order Verification System** for Burk.pk (Devomech Solutions).

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
- A pluggable **channel-connector** interface with development-only simulated Burk/Daraz feeds (deliberately different shapes, normalised to one model). These fixtures verify the internal contract but are not evidence of a live platform connection; live completion requires approved API access and staging acceptance.
- **Idempotent ingestion** keyed on `(channel, external_id)` with an append-only **`SyncRun`** reconciliation ledger — every sync satisfies `fetched == created + updated + duplicates_skipped + failed`, so **no record is dropped or duplicated** (project KPI #3).
- An **Orders** console screen: unified queue, channel/status filters, search, a **Sync now** button, and a live `0 dropped · 0 duplicated · N unique` integrity badge; plus an order-detail view with product-resolved lines and the raw channel payload.

**Module 3 (Intelligent Fulfilment & Barcode Verification)** is complete:

- A **packing station**: pick an order from the queue, work a digital packing list, and **scan each item's barcode** before sealing.
- **Real-time mismatch interception** — scanning an item that doesn't belong to the order flashes a full-screen red warning and sounds an audio buzz to block it (project KPI #1). Every scan, matched or not, is written to an append-only **`PackScan`** ledger, so 100% interception is auditable (`check_pack_integrity`).
- Keyboard-wedge friendly: the scan input works with a real barcode/QR scanner, manual typing, or the on-screen simulate buttons — identically.
- Completing a pack decrements stock through the ledger (`SALE` movements) and marks the order **Packed** — this is where Module 2's deferred stock movement finally happens.

**Module 4 (Automated Video Surveillance & Customer Transparency)** is complete:

- Recording starts when the packing session starts, so the whole packaging
  sequence is covered. Completing the pack only seals the recording and writes
  durable video/notification jobs; FFmpeg and provider I/O run outside the HTTP
  request in the leased worker.
- The overhead-camera adapter is simulated here because no physical camera is
  connected. The worker still creates a real clip and genuinely re-encodes it
  with FFmpeg; RTSP/USB capture is an adapter swap.
- A shared, idempotent **`Notification` outbox** (also used by Modules 5 and 6)
  records queued, processing, retrying, sent, and failed states, provider
  acknowledgement, and latency. `check_dispatch_latency` requires both
  configured channels, non-empty acknowledged evidence, no duplicate/pending/
  failed rows, and every packaging-video acknowledgement within **3 minutes**
  of sealing (project KPI #2).
- Videos are never exposed through `/media/`. Operators use an authenticated
  endpoint; customer messages contain a checksum-bound, expiring signed link.
  Raw clips are never routable, and retention cleanup preserves the audit row.
- Email goes through Django's real mail backend (console in dev, one env var
  away from real SMTP/SendGrid). WhatsApp has no real credentials available in
  this environment, so it's a simulated Cloud-API-shaped adapter; a real
  integration is a documented drop-in (`notifications/channels/live_whatsapp.py`).

**Module 5 (Logistics Integration & Automated Tracking)** is complete:

- **Automatic Airway Bill Booking** — pack completion atomically enqueues one
  idempotent courier job. The worker books a courier (Leopard / TCS / Trax / M&P
  in the simulated adapter), records the tracking number, and flips the order to
  **Shipped** without manual data entry. Provider outages retry with bounded
  backoff and remain visibly failed if attempts are exhausted.
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
- The same durable worker automatically claims the reminder when
  `scheduled_for` becomes due. `dispatch_scheduled_notifications` remains as a
  bounded operational compatibility command, not a required manual cron step.

## Completion boundary

All seven planned software modules (0–6) are implemented and have automated,
PostgreSQL, integrity-command, and browser acceptance coverage. The repository
is **code-complete and demo-complete** with its simulated adapters. It is not
honest to call the external rollout live-complete until the organization supplies
and accepts the real dependencies:

- Daraz Open Platform app key/secret/access token and seller staging access.
- Burk.pk's real order source contract (REST/webhook/database) and credentials.
- The warehouse camera/RTSP or USB device and deployment host.
- Courier sandbox/production credentials and webhook contract.
- WhatsApp Cloud API credentials/templates and a real SMTP/email provider.

Set `REQUIRE_LIVE_INTEGRATIONS=True` in release/staging. The operational health
gate then returns unhealthy while any configured adapter still reports
`mode=simulated`, preventing a simulated setup from being presented as a live
release. Live-provider acceptance is an environment/credential milestone, not
missing internal application logic.

Adapter selection never requires a source-code edit:

| Dependency | Development value | Live value |
|---|---|---|
| Burk/Daraz orders | `ORDER_CONNECTOR_BACKENDS={"burk":"fixture","daraz":"fixture"}` | `{"burk":"live","daraz":"live"}` |
| Packaging camera | `PACKAGING_CAMERA_BACKEND=simulated` | `live` |
| Courier | `COURIER_BACKEND=simulated` | `live_leopard` |
| WhatsApp | `WHATSAPP_BACKEND=simulated` | `live` |
| Review destination | `REVIEW_LINK_BACKEND=simulated` | `live_burk` |

Fixture/simulated values are deliberately refused whenever
`PRODUCTION_MODE=True`, even if a stale environment accidentally leaves
`DEMO_MODE_ENABLED=True`. The `/api/health/` readiness response
names missing settings but never returns their values.

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

### 3. Backend API

```bash
cd backend
uv run python manage.py migrate
uv run python manage.py seed_demo      # demo users, products, suppliers, stock
uv run python manage.py runserver 127.0.0.1:8000
```

### 4. Durable worker (new terminal — required)

```bash
cd backend
uv run python manage.py run_worker --worker-name=local-worker
```

The API deliberately does not perform FFmpeg, notification-provider, or courier
I/O inline. Keep one worker running anywhere those features are expected. The
dashboard shows a stale/missing heartbeat as **Not ready**.

### 5. Frontend (new terminal)

```bash
cd frontend
npm install
npm run dev               # http://localhost:3001
```

### 6. Log in

Open **http://localhost:3001** and sign in:

| User | Password | Sees |
|---|---|---|
| `manager` | `burkdemo123` | Everything, including supplier & PO actions |
| `operator` | `burkdemo123` | Dashboard, Orders, own Packing sessions, and Inventory; no supplier/PO/Manager actions |

## Production security profile

Local development keeps HTTP, demo actions, and fixture data enabled. A real
deployment must set `DEBUG=False` and `PRODUCTION_MODE=True`, provide a strong
environment-only `SECRET_KEY`, use the public HTTPS host/origin, and explicitly
disable all demo/reset switches. With those values, secure cookies, HTTPS
redirects, one-year HSTS (including subdomains/preload), and the trusted proxy
scheme header are enabled by default. Only enable `TRUST_X_FORWARDED_PROTO` when
the reverse proxy is trusted and always overwrites that header.

The production environment should include at least:

```dotenv
DEBUG=False
PRODUCTION_MODE=True
SECRET_KEY=<strong secret from the deployment secret store>
ALLOWED_HOSTS=scm.example.com
FRONTEND_ORIGIN=https://scm.example.com
PUBLIC_APP_ORIGIN=https://scm.example.com
REQUIRE_LIVE_INTEGRATIONS=True
DEMO_MODE_ENABLED=False
DEMO_ACTIONS_ENABLED=False
ALLOW_DEMO_RESET=False
ORDER_CONNECTOR_BACKENDS={"burk":"live","daraz":"live"}
PACKAGING_CAMERA_BACKEND=live
COURIER_BACKEND=live_leopard
WHATSAPP_BACKEND=live
REVIEW_LINK_BACKEND=live_burk
STATIC_ROOT=/srv/burk-scm/static
MEDIA_ROOT=/srv/burk-scm/media
```

Validate the effective deployment settings before release:

```bash
cd backend
uv run python manage.py check --deploy --fail-level WARNING
```

The command must exit zero. Packaging media is served only by the authorized,
signed `/api/recordings/<id>/video/` endpoint; production should place the
underlying objects in durable private storage and run the retention command on a
schedule. The public `/media/` route is intentionally absent, including in dev.

### Reproducible production stack

The production topology is defined in `compose.prod.yml`: PostgreSQL, a one-shot
migration/static-collection job, Gunicorn API, durable worker, standalone
Next.js server, and nginx. All application containers run as non-root users.
Only nginx publishes a port, bound to `127.0.0.1` by default; PostgreSQL, API,
frontend, and private media are never host-published.

```bash
cp .env.production.example .env.production
chmod 600 .env.production
# Replace every placeholder and complete the external-integration acceptance.

BURK_SCM_ENV_FILE=.env.production \
  docker compose --env-file .env.production -f compose.prod.yml config --quiet
BURK_SCM_ENV_FILE=.env.production \
  docker compose --env-file .env.production -f compose.prod.yml up -d --build
BURK_SCM_ENV_FILE=.env.production \
  docker compose --env-file .env.production -f compose.prod.yml ps
```

Place a trusted TLS terminator (host nginx/Caddy or a load balancer) in front of
`127.0.0.1:8080`, restrict that port to the terminator, and make it overwrite
`X-Forwarded-Proto`. The bundled nginx supplies security headers, denies
`/media/`, serves only collected static assets, and proxies protected recording
responses through Django. Do not use `docker compose down -v` in operations:
`-v` deletes the named database/media volumes.

The complete deployment, scheduling, backup/restore, rollback, monitoring,
secret-rotation, and incident procedure is in
[`docs/operations/production-runbook.md`](docs/operations/production-runbook.md).

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

1. Stop the worker temporarily, then click **Complete pack**. The station
   immediately and truthfully shows **Queued for processing** and **Courier
   booking queued**; stock/order changes are already committed, but no external
   I/O ran in the request. Restart the worker.
2. The page polls boundedly and changes through Processing/Retrying/Failed/Ready.
   On success it shows a playable protected video plus Email/WhatsApp provider
   acknowledgement and exact latency (well under the 3-minute KPI in the demo).
3. It also shows a **Shipment** panel: courier, tracking number, and a
   **Simulate: mark in transit / mark delivered** button pair (there's no real
   courier webhook in this environment, so this stands in for one). The same
   panel — plus the full notification history — is on the order's own detail
   page (**Orders** → open an order).
4. Click **Simulate: mark delivered** → the order flips to **Delivered** and a
   review-request notification is **scheduled** (not sent instantly — see it
   listed as "Scheduled" in Customer notifications). Keep the worker running;
   after `REVIEW_REMINDER_DELAY_SECONDS` (60s by default) it automatically flips
   to **Sent**. The management command can perform a bounded due-job drain for
   operations/testing, but normal processing does not depend on it.

## Useful commands

```bash
cd backend
uv run python manage.py test                        # full test suite
uv run python manage.py run_worker --worker-name=local-worker  # required durable worker (continuous)
uv run python manage.py run_worker --once           # process one bounded due-work batch
uv run python manage.py recalculate_stock --check    # prove ledger == cache (exits non-zero on drift)
uv run python manage.py check_order_integrity --check        # prove no dropped/duplicated orders — KPI #3 (exits non-zero on drift)
uv run python manage.py check_pack_integrity --check         # prove no mismatch was ever packed — KPI #1 (exits non-zero on breach)
uv run python manage.py check_dispatch_latency --check       # prove every video dispatched within 3 min — KPI #2 (exits non-zero on breach)
uv run python manage.py check_shipment_integrity --check     # prove courier booking is never a manual gap
uv run python manage.py check_operational_health --check     # DB, worker, backlog, media, adapter readiness
uv run python manage.py check_operational_metrics --check    # bounded queue/source/KPI/media threshold gate
uv run python manage.py check_release_policy                 # block unsafe/demo/simulated production configuration
uv run python manage.py cleanup_packaging_media --check      # audit retention eligibility/safety
uv run python manage.py cleanup_packaging_media --dry-run    # preview retention cleanup
uv run python manage.py cleanup_packaging_media              # apply configured raw/compressed retention
uv run python manage.py sync_orders                  # pull channel feeds into the queue (CLI "Sync now")
uv run python manage.py simulate_new_order --channel daraz     # inject one demo order for the next sync
uv run python manage.py simulate_delivery_update SO-00001 --status delivered   # simulate a courier webhook
uv run python manage.py dispatch_scheduled_notifications        # bounded compatibility drain for due notification jobs
# Guarded and scoped: removes only deterministic demo-owned rows and requires
# both an environment opt-in and an explicit confirmation flag.
ALLOW_DEMO_RESET=True uv run python manage.py seed_demo --reset --confirm-reset
```

## How it fits together

- The frontend reaches the API through a **Next rewrites proxy** (`/api/*` → `127.0.0.1:8000`), so the browser only ever sees one origin — no CORS, and the session cookie is sent normally. CSRF is still enforced (`CSRF_TRUSTED_ORIGINS` covers `localhost:3001`).
- Every stock change goes through `inventory.services.record_movement()` — one writer, one transaction, row-locked. The ledger is the source of truth; `quantity_on_hand` is a cache of it.
- Order ingestion goes through `orders.services.ingest_channel()` — idempotent on `(channel, external_id)`, one `SyncRun` per channel per sync. The unique constraint guarantees no duplicates; the reconciliation invariant guarantees nothing fetched is dropped. Order ingestion does **not** touch stock — that happens later at fulfilment (Module 3).
- Barcode verification goes through `fulfillment.services` — every scan is appended to the `PackScan` ledger (matched, mismatch, or overscan), and only a `complete_packing` with all lines fully scanned decrements stock (`SALE` movements) and marks the order Packed. A mismatch is recorded but can never advance the pack, which is what makes KPI #1 auditable.
- Packing start calls `surveillance.services.start_recording()`. Completion is one short database transaction: `complete_packing()` commits stock/order state, `seal_and_enqueue_recording()` seals the capture, and `enqueue_shipment_booking()` writes the courier job. No camera stop, FFmpeg, provider send, or courier call runs in that HTTP request.
- `operations` is the durable execution boundary. `WorkItem` rows use unique business keys, PostgreSQL leased claims (`select_for_update(skip_locked=True)`), bounded exponential retry, terminal failure, correlation IDs, and worker heartbeats. Restarting a worker reclaims expired leases without repeating the stock sale.
- `notifications.services.dispatch()` is the single outbox writer behind every customer-facing message. It atomically persists one idempotent row/job per order event and channel; the worker records provider acknowledgement. `sent_at - reference_event_at` is the literal KPI #2 number, and `check_dispatch_latency` rejects missing channels, empty evidence, duplicates, unacknowledged sends, pending/retrying/failed rows, or latency over 180 seconds. Future review reminders are ordinary jobs with a future `available_at`, so the worker picks them up automatically when due.
- Packaging video delivery goes through `surveillance.views.recording_video`: a logged-in Manager or the packing-session owner may stream it, while customers require an expiring checksum-bound token. Range requests are supported for browser playback; raw media, traversal, symlinks, and checksum mismatches are rejected.
- A courier delivery update — real webhook in production, `simulate_delivery_update` here — goes through `logistics.services.advance_shipment()`, which appends a `ShipmentEvent` and, on `DELIVERED`, both flips the order and schedules Module 6's review reminder. There is no dedicated "Module 6" app: it's this one trigger plus the shared notification scheduler.

## Project layout

```
burk-scm/
├── docker-compose.yml         # postgres:16 on host port 5433
├── .env.example
├── backend/                   # Django + DRF
│   ├── config/                # settings, urls
│   ├── common/                # permissions, correlation IDs, JSON logs, health + Manager metrics
│   ├── operations/            # durable leased work queue + worker heartbeat
│   ├── accounts/              # custom User + roles + auth API
│   ├── inventory/             # Category, Product, StockMovement, services, API
│   ├── suppliers/             # Supplier, SupplierProduct, price tiers, API
│   ├── purchasing/            # PurchaseOrder + lines, reorder/submit/receive
│   ├── orders/                # SalesOrder queue, channel connectors, idempotent sync + reconciliation
│   ├── fulfillment/           # PackingSession + append-only PackScan, scan validation
│   ├── surveillance/          # Module 4: capture lifecycle, FFmpeg, signed streaming, retention
│   ├── logistics/             # Module 5: courier booking, append-only ShipmentEvent log; Module 6's delivery trigger
│   └── notifications/         # Shared append-only Notification ledger + Email/WhatsApp channel adapters (Modules 4-6)
└── frontend/                  # Next.js console (login, dashboard, orders, packing, inventory, suppliers, POs)
```
