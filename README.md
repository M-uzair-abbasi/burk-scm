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

Later modules (barcode verification, packaging video, logistics, post-delivery review) are **not** built yet.

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

## Useful commands

```bash
cd backend
uv run python manage.py test                    # full test suite (45 tests)
uv run python manage.py recalculate_stock --check   # prove ledger == cache (exits non-zero on drift)
uv run python manage.py check_order_integrity       # prove no dropped/duplicated orders — KPI #3 (exits non-zero on drift)
uv run python manage.py sync_orders                 # pull channel feeds into the queue (CLI "Sync now")
uv run python manage.py simulate_new_order --channel daraz   # inject one demo order for the next sync
uv run python manage.py seed_demo --reset       # wipe and reseed demo data (runs an initial order sync)
```

## How it fits together

- The frontend reaches the API through a **Next rewrites proxy** (`/api/*` → `127.0.0.1:8000`), so the browser only ever sees one origin — no CORS, and the session cookie is sent normally. CSRF is still enforced (`CSRF_TRUSTED_ORIGINS` covers `localhost:3001`).
- Every stock change goes through `inventory.services.record_movement()` — one writer, one transaction, row-locked. The ledger is the source of truth; `quantity_on_hand` is a cache of it.
- Order ingestion goes through `orders.services.ingest_channel()` — idempotent on `(channel, external_id)`, one `SyncRun` per channel per sync. The unique constraint guarantees no duplicates; the reconciliation invariant guarantees nothing fetched is dropped. Order ingestion does **not** touch stock — that happens later at fulfilment (Module 3).

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
│   └── orders/                # SalesOrder queue, channel connectors, idempotent sync + reconciliation
└── frontend/                  # Next.js console (login, dashboard, orders, inventory, suppliers, POs)
```
