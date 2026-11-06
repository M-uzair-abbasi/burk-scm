# Authorization and Administrative Safety Gate — Verification Results

**Date:** 2026-08-16  
**Branch:** `codex/production-completion`  
**Scope:** Production-completion Gate 2

## Outcome

Gate 2 passes for all locally controllable authorization, authentication,
administrative-safety, demo-reset, and production-settings requirements. This
does not satisfy the later secure-media/background-worker gate or any live
external-integration gate.

## PostgreSQL regression

```bash
cd backend
uv run python manage.py test
```

Result: **137 tests passed** in 172.487 seconds on PostgreSQL, including:

- anonymous/Operator/Manager synchronization authorization;
- anonymous/Operator/Manager simulated-shipment authorization;
- shipment simulation disabled outside demo mode;
- stock-below-zero Manager override and mandatory audit-note enforcement;
- per-account and per-address login throttling;
- read-only workflow/ledger Admin models and inlines;
- non-privileged demo users, including safe downgrade of the former demo superuser;
- triple-gated, selectively scoped demo reset with unrelated-data/media preservation;
- production settings and Django deployment checks.

## Production settings verification

With `DEBUG=False`, `PRODUCTION_MODE=True`, a strong environment secret, an
HTTPS host/origin, and every demo switch disabled:

```bash
uv run python manage.py check --deploy --fail-level WARNING
```

Result: exit 0, no warnings. The effective profile enabled HTTPS redirect,
secure session/CSRF cookies, one-year HSTS with subdomains/preload, and the
trusted proxy scheme tuple. `.env` remains excluded by `.gitignore`, and
`makemigrations --check --dry-run` reported no changes.

## Isolated acceptance database

Acceptance reused the isolated `burk_gate1_accept_20260816` database, applied
all current migrations, and reran `seed_demo` without a destructive reset. The
recognized legacy demo Manager was safely downgraded:

```text
manager  role=manager   is_staff=False  is_superuser=False
operator role=operator  is_staff=False  is_superuser=False
```

All integrity commands exited 0:

- Stock: 9 products, zero ledger/cache drift.
- Orders: 0 dropped, 0 duplicated, 10 unique.
- Packing: 1 qualifying completed pack and 1 accepted scan.
- Packaging dispatch: 2 sent, maximum 0.4 seconds, zero failed/overdue.
- Shipment: 1 automatically booked shipment, no integrity breach.

## Browser role acceptance

The production Next.js build ran against the isolated PostgreSQL backend.

Manager-visible controls:

- Suppliers and Purchase Orders navigation;
- Sync Now on the aggregated order queue;
- Reorder and Allow below zero on product detail;
- simulated courier advancement on shipment detail.

Operator checks returned a visible-control count of zero for every one of those
Manager-only actions while retaining Dashboard, Orders, Packing, and Inventory
read/operational access. The backend regression suite independently proved the
corresponding direct API calls return 403, so the boundary does not rely on UI
hiding. Browser warning/error log count: zero.

## Safety behavior verified

- A reset is rejected unless demo mode, `ALLOW_DEMO_RESET=True`, and
  `--confirm-reset` are all present.
- Rejected resets make no database change.
- A confirmed reset removes only deterministic demo users, SKUs, supplier
  codes, feed order keys, related workflow rows, their media paths, and
  `*_injected.json` files.
- An unrelated user, product, movement, supplier, sales order, media object,
  and feed file survived the confirmed-reset test.
- Workflow and ledger records cannot be added, edited, or deleted through
  Django Admin, even by a superuser; validated services remain the only writers.

## Remaining gates

The next locally controllable gate is reliable asynchronous processing, secure
media delivery/retention, and observability. Live Daraz/Burk, courier,
WhatsApp/email, camera, object-storage/CDN, and deployment acceptance remain
external blockers until their credentials, contracts, infrastructure, and
hardware are supplied.
