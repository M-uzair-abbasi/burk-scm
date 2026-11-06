# Authorization and Administrative Safety Plan

> **Execution:** Follow test-first red-green-refactor, one task at a time. PostgreSQL is authoritative. Do not commit without the user's explicit request.

**Goal:** Complete production Gate 2 by enforcing the Manager/Operator matrix at the API and service layers, rate-limiting authentication, making workflow history immutable in Admin, preventing destructive demo resets, and providing a deploy-check-clean production settings profile.

**Spec:** `docs/superpowers/specs/2026-08-16-production-completion-design.md`

---

### Task 1: Enforce Manager-only operational actions

**Files:** `backend/common/permissions.py`, `backend/orders/views.py`, `backend/orders/tests.py`, `backend/logistics/views.py`, `backend/logistics/tests.py`, `backend/config/settings.py`, `frontend/src/app/(app)/orders/page.tsx`, `frontend/src/app/(app)/orders/[id]/page.tsx`

- [x] Add failing anonymous/Operator/Manager API tests for order sync and simulated shipment advancement.
- [x] Add `IsManager`; keep order/shipment reads authenticated while requiring it for `sync` and `advance`.
- [x] Add `DEMO_ACTIONS_ENABLED` and return 404 for simulated shipment advancement when disabled.
- [x] Hide Sync Now and simulated courier controls from Operators.
- [x] Run focused backend tests plus frontend type-check/lint.

### Task 2: Protect negative-stock overrides

**Files:** `backend/inventory/services.py`, `backend/inventory/views.py`, `backend/inventory/tests.py`, `frontend/src/app/(app)/inventory/[id]/page.tsx`

- [x] Add failing service/API tests: Operator override is 403, Manager without an audit note is 400, and Manager with an explicit note creates one auditable movement.
- [x] Enforce the Manager role and mandatory non-blank note inside `record_movement()` whenever an operation would put stock below zero.
- [x] Translate service permission failures to HTTP 403 and expose the override checkbox only to Managers.
- [x] Run inventory tests, ledger reconciliation, type-check, and lint.

### Task 3: Rate-limit login attempts

**Files:** `backend/accounts/throttles.py`, `backend/accounts/views.py`, `backend/accounts/tests.py`, `backend/config/settings.py`, `.env.example`

- [x] Add failing tests proving repeated bad attempts receive 429 while a normal login succeeds.
- [x] Add address-wide and username-and-address keyed DRF throttles with environment-configured rates.
- [x] Apply them only to the login endpoint and document both rates.
- [x] Run accounts tests and Django checks.

### Task 4: Make workflow data immutable in Admin and safe demo users non-privileged

**Files:** `backend/common/admin.py`, workflow app `admin.py` files, `backend/common/tests.py`, `backend/inventory/management/commands/seed_demo.py`

- [x] Add failing tests asserting workflow/ledger Admin registrations reject add/change/delete even for a superuser.
- [x] Introduce reusable read-only Admin and inline mixins; apply them to stock movements, purchase orders/lines, sales orders/lines, sync runs, packing sessions/scans, recordings, notifications, shipments/events.
- [x] Add a seed test proving demo Manager and Operator are neither staff nor superusers; safely downgrade only recognized demo accounts from older seeds.
- [x] Run common/admin and seed tests.

### Task 5: Guard and scope demo reset

**Files:** `backend/config/settings.py`, `backend/inventory/management/commands/seed_demo.py`, `backend/inventory/tests.py`, `.env.example`, `README.md`

- [x] Add failing tests proving reset is rejected unless demo mode, `ALLOW_DEMO_RESET`, and `--confirm-reset` are all present, with no data changed.
- [x] Replace global table deletion with deletion limited to deterministic demo users/SKUs/supplier codes/feed order keys and their related lifecycle rows.
- [x] Delete only media paths belonging to deleted demo recordings and clear only generated `*_injected.json` feed files after database commit.
- [x] Prove an unrelated user, product, supplier, order, movement, and media file survive a confirmed reset.
- [x] Document the guarded reset command and run focused tests.

### Task 6: Add a deploy-check-clean production security profile

**Files:** `backend/config/settings.py`, `.env.example`, `README.md`, `backend/common/tests.py`

- [x] Add tests for secure production defaults: HTTPS redirect, secure cookies, HSTS, trusted proxy header, non-debug demo actions, and non-disposable reset.
- [x] Read security values from environment with safe non-debug defaults; keep local development behavior unchanged.
- [x] Add a documented production environment example and run `manage.py check --deploy --fail-level WARNING` with production values.
- [x] Verify no secrets are committed and migrations remain clean.

### Task 7: Gate 2 regression and evidence

**Files:** `docs/verification/2026-08-16-authorization-admin-safety-results.md`

- [x] Run the complete PostgreSQL backend suite and every integrity command against isolated acceptance data.
- [x] Run frontend type-check, lint, and production build.
- [x] Browser-check Manager/Operator visibility and API-check all forbidden actions.
- [x] Record exact evidence and external blockers; mark Gate 2 complete only when every locally controllable row passes.
