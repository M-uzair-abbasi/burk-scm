# Core Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the data-integrity, concurrency, authorization, and false-positive KPI gaps in Modules 1–4 before any production integration work begins.

**Architecture:** Preserve the existing Django service boundaries and append-only ledgers. Add validation at connector and service boundaries, lock fresh PostgreSQL rows before lifecycle transitions, separate channel-reported state from Burk's internal workflow state, and make every KPI check require non-empty successful evidence. API and frontend responses expose partial failures instead of presenting them as success.

**Tech Stack:** Django 5.2, Django REST Framework, PostgreSQL 16, Next.js 16, React 19, TypeScript, Django `TestCase`/`TransactionTestCase`.

**Spec:** `docs/superpowers/specs/2026-08-16-production-completion-design.md`

## Global Constraints

- PostgreSQL, not SQLite, is authoritative for concurrency acceptance.
- Every production behavior change follows test-first red-green-refactor.
- Existing public routes remain stable unless this plan explicitly changes their response fields or status semantics.
- Stock, scan, sync, and shipment audit records remain append-only.
- Simulated connectors remain available only as development/test implementations and do not satisfy live-completion gates.
- No Git commit is created unless the user explicitly asks for one.
- Preserve the user's pre-existing uncommitted UUID media-filename change in `backend/surveillance/services.py`.

---

### Task 1: Reject empty/invalid packs and close the manual-barcode bypass

**Files:**
- Modify: `backend/fulfillment/tests.py`
- Modify: `backend/fulfillment/services.py`
- Modify: `backend/orders/models.py`
- Create: `backend/orders/migrations/0002_salesorderline_quantity_positive.py`
- Modify: `backend/fulfillment/management/commands/check_pack_integrity.py`

**Interfaces:**
- Consumes: `start_packing(order, user=None)`, `session_progress(session)`, `confirm_line_manual(session, line, user=None)`.
- Produces: pack validation requiring at least one positive-quantity line; `session_progress(...)["complete"]` is false for an empty order; KPI #1 fails on zero qualifying completed sessions.

- [x] **Step 1: Write failing service tests**

Add tests whose production mutations are: removing the non-empty guard, accepting zero quantity, or deleting the barcode guard.

```python
def test_empty_order_cannot_start_packing(self):
    order = make_order(lines=[])
    with self.assertRaisesMessage(ValidationError, "at least one line"):
        start_packing(order)

def test_empty_order_is_never_complete(self):
    order = make_order(lines=[])
    session = PackingSession.objects.create(order=order)
    self.assertFalse(session_progress(session)["complete"])

def test_manual_confirm_rejects_barcoded_line(self):
    product = make_product("BRK-A", "1111")
    order = make_order(lines=[(product, 1)])
    session = start_packing(order)
    with self.assertRaisesMessage(ValidationError, "must be scanned"):
        confirm_line_manual(session, order.lines.get())
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
uv run python manage.py test \
  fulfillment.tests.SessionLifecycleTests.test_empty_order_cannot_start_packing \
  fulfillment.tests.SessionLifecycleTests.test_empty_order_is_never_complete \
  fulfillment.tests.ManualConfirmTests.test_manual_confirm_rejects_barcoded_line
```

Expected: all three fail because current behavior accepts the invalid operations.

- [x] **Step 3: Implement the minimum service and database guards**

Add one validation helper in `fulfillment.services`:

```python
def _validate_packable_lines(order: SalesOrder) -> list[SalesOrderLine]:
    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ValidationError(f"{order.reference} must contain at least one line.")
    if any(line.quantity <= 0 for line in lines):
        raise ValidationError(f"{order.reference} contains a non-positive quantity.")
    return lines
```

Call it from `start_packing()` and `complete_packing()`. Initialize overall progress as `bool(lines)` rather than `True`. In `confirm_line_manual()`, reject a line when `line.product_id` exists and `line.product.barcode` is non-empty. Add a `CheckConstraint(condition=Q(quantity__gt=0), name="sales_order_line_qty_positive")` and generate migration `0002`.

- [x] **Step 4: Extend the KPI command tests and implementation**

Add command tests using `call_command("check_pack_integrity", "--check")` proving that zero completed sessions and a database-created completed empty session raise `SystemExit(1)`. Update the command to report `qualifying_sessions`, empty-session breaches, positive-quantity breaches, and require at least one non-empty completed session.

- [x] **Step 5: Run Task 1 verification**

Run:

```bash
cd backend
uv run python manage.py test fulfillment
uv run python manage.py makemigrations --check --dry-run
```

Expected: fulfilment tests pass and Django reports no missing migrations.

---

### Task 2: Enforce packing-session ownership at the API boundary

**Files:**
- Modify: `backend/fulfillment/tests.py`
- Modify: `backend/fulfillment/views.py`
- Modify: `backend/fulfillment/services.py`

**Interfaces:**
- Consumes: authenticated `request.user`, `User.is_manager`, `PackingSession.operator`.
- Produces: only the assigned Operator or any Manager can retrieve or mutate a session; starting an already-owned session does not transfer ownership implicitly.

- [x] **Step 1: Write failing API authorization tests**

Use DRF `APIClient` with an owner Operator, a second Operator, and a Manager. Assert the second Operator receives 404 or 403 for retrieve, scan, confirm-line, complete, and cancel, while the owner and Manager can retrieve. Also assert the second Operator cannot claim an order whose active session belongs to the owner.

```python
def test_non_owner_cannot_scan_session(self):
    self.client.force_authenticate(self.other_operator)
    response = self.client.post(
        f"/api/packing/{self.session.id}/scan/", {"barcode": "1111"}, format="json"
    )
    self.assertEqual(response.status_code, 404)
    self.assertFalse(self.session.scans.exists())
```

- [x] **Step 2: Run authorization tests and verify RED**

Run `uv run python manage.py test fulfillment.tests.PackingAuthorizationTests`.

Expected: non-owner requests currently succeed.

- [x] **Step 3: Scope session lookup and active-session resume**

Implement `PackingViewSet.get_queryset()` so Managers see all sessions and Operators see only `operator=request.user`. Use `self.get_queryset()` in object lookup. In `create()`, detect an existing active session before invoking `start_packing`; return 403 when it belongs to a different Operator unless the caller is a Manager. A Manager resume preserves the original operator rather than silently reassigning it.

- [x] **Step 4: Run Task 2 verification**

Run:

```bash
cd backend
uv run python manage.py test fulfillment.tests.PackingAuthorizationTests
uv run python manage.py test fulfillment
```

Expected: all ownership cases and existing fulfilment behavior pass.

---

### Task 3: Serialize packing completion and PO receipt on authoritative rows

**Files:**
- Modify: `backend/fulfillment/tests.py`
- Modify: `backend/fulfillment/services.py`
- Modify: `backend/purchasing/tests.py`
- Modify: `backend/purchasing/services.py`

**Interfaces:**
- Consumes: `complete_packing(session, user=None)`, `receive_po(po, receipts=None, user=None)`.
- Produces: concurrent duplicate completion/receipt causes one stock effect; a completed pack may be safely retried and returns its order.

- [x] **Step 1: Write PostgreSQL concurrency regression tests**

Add `TransactionTestCase` tests using two threads, separate database connections, and a barrier. Both callers operate on independently fetched model instances. Assert:

```python
self.assertEqual(
    StockMovement.objects.filter(reason=StockMovement.Reason.SALE, note__contains=order.reference).count(),
    1,
)
self.assertEqual(Product.objects.get(pk=product.pk).quantity_on_hand, 9)
```

For a full PO receipt, assert exactly one purchase-receipt movement, `quantity_received == quantity_ordered`, and one stock increase.

- [x] **Step 2: Run both concurrency tests and verify RED on PostgreSQL**

Run:

```bash
cd backend
uv run python manage.py test \
  fulfillment.tests.ConcurrentPackingCompletionTests \
  purchasing.tests.ConcurrentReceiptTests
```

Expected: at least one current race assertion fails or a database error exposes stale-instance state checks.

- [x] **Step 3: Lock fresh rows before checking state**

At the start of `complete_packing()`, re-fetch `PackingSession` with `select_for_update()` and `select_related("order")`, then lock the `SalesOrder`. Return the already-completed order for a retry; reject cancelled sessions. Build progress from the locked session.

At the start of `receive_po()`, re-fetch the PO with `select_for_update()` and fetch receipt lines through `PurchaseOrderLine.objects.select_for_update().filter(purchase_order=locked_po)`. Perform all status and outstanding checks on these fresh locked rows. A second caller that observes `RECEIVED` returns the PO without creating a movement when it represents an identical full-receipt retry; other invalid state changes remain validation errors.

- [x] **Step 4: Run Task 3 verification**

Run the two focused concurrency classes twice, then run:

```bash
uv run python manage.py test fulfillment purchasing inventory
uv run python manage.py recalculate_stock --check
```

Expected: both repeated concurrency runs pass and ledger/cache drift is zero.

---

### Task 4: Preserve supplier pricing and effective lead-time snapshots

**Files:**
- Modify: `backend/purchasing/models.py`
- Create: `backend/purchasing/migrations/0002_purchaseorderline_supplier_snapshot.py`
- Modify: `backend/purchasing/services.py`
- Modify: `backend/purchasing/serializers.py`
- Modify: `backend/purchasing/tests.py`
- Modify: `frontend/src/lib/types.ts`

**Interfaces:**
- Consumes: `SupplierProduct.effective_lead_time_days`, `SupplierProduct.unit_price_for(quantity)`.
- Produces: `PurchaseOrderLine.supplier_product`, `effective_lead_time_days`, and `price_tier_min_quantity` historical snapshots; submission uses the maximum preserved line lead time.

- [x] **Step 1: Write failing snapshot tests**

Set a supplier default of 12 days and a supplier-product override of 4 days. Create a reorder PO, then change both supplier and supplier-product values before submission. Assert the line still stores 4 and submission uses four days. Assert its tier snapshot equals 60 for a quantity of 60.

- [x] **Step 2: Run focused purchasing tests and verify RED**

Run `uv run python manage.py test purchasing.tests.PurchasingServiceTests.test_submit_uses_preserved_supplier_product_lead_time`.

Expected: current submission uses 12 days and the snapshot fields do not exist.

- [x] **Step 3: Add snapshot fields and populate them at draft creation**

Add nullable `supplier_product = ForeignKey(..., on_delete=PROTECT)`, positive `effective_lead_time_days`, and positive nullable `price_tier_min_quantity`. Add `SupplierProduct.price_tier_for(quantity)` returning the selected `SupplierPriceTier | None`, and make `unit_price_for(quantity)` delegate to it. Pass the selected relationship, lead time, tier minimum, and price through `create_po`. `submit_po()` uses `max(line.effective_lead_time_days for line in po.lines.all())`.

- [x] **Step 4: Expose snapshots and verify**

Add the fields to the read serializer and matching TypeScript interface. Run:

```bash
cd backend
uv run python manage.py test purchasing suppliers
uv run python manage.py makemigrations --check --dry-run
cd ../frontend
npx tsc --noEmit
```

Expected: tests and type-check pass with no migration drift.

---

### Task 5: Separate source status and freeze lines after packing starts

**Files:**
- Modify: `backend/orders/models.py`
- Create: `backend/orders/migrations/0003_salesorder_source_status.py`
- Modify: `backend/orders/services.py`
- Modify: `backend/orders/serializers.py`
- Modify: `backend/orders/tests.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/app/(app)/orders/[id]/page.tsx`

**Interfaces:**
- Consumes: `NormalizedOrder.status`, existing internal `SalesOrder.status`, packing-session history.
- Produces: `SalesOrder.source_status`; source synchronization cannot rewind internal fulfilment or delete line snapshots once packing has begun.

- [x] **Step 1: Write failing lifecycle-preservation tests**

Create and locally pack an order, retain its line and scan IDs, then ingest the same external ID as `pending` with different lines. Assert internal status remains `packed`, `source_status == pending`, original lines remain, and `PackScan.line_id` remains unchanged. Add a second test proving an untouched source-managed order can move from pending to cancelled/shipped according to the source.

- [x] **Step 2: Run focused tests and verify RED**

Run:

```bash
uv run python manage.py test \
  orders.tests.IngestionServiceTests.test_resync_cannot_rewind_locally_packed_order \
  orders.tests.IngestionServiceTests.test_resync_preserves_lines_after_packing_started
```

Expected: current code rewinds status and rebuilds lines.

- [x] **Step 3: Replace destructive update-or-create logic**

Add `source_status` as an indexed status-choice field. Migration `0003` first adds the field, then runs a data migration that copies each existing row's `status` into `source_status`, preserving current source history. In `_upsert_order`, lock and fetch the existing order by `(channel, external_id)`. On creation, initialize both statuses from the source. On update, always update `source_status`, source customer/totals/raw payload, and sync timestamp. Mirror source into internal status only when no packing session exists and the order has not entered a locally controlled lifecycle. Replace lines only when no packing session exists; otherwise preserve the immutable snapshot and record a discrepancy marker in sync details.

- [x] **Step 4: Expose source status and verify**

Add `source_status` and display label to serializers/types/order detail UI. Run:

```bash
cd backend
uv run python manage.py test orders fulfillment
uv run python manage.py makemigrations --check --dry-run
cd ../frontend
npx tsc --noEmit
```

Expected: order and fulfilment regressions pass, with source/internal state both visible.

---

### Task 6: Account for every raw channel record independently

**Files:**
- Modify: `backend/orders/connectors/base.py`
- Modify: `backend/orders/services.py`
- Modify: `backend/orders/tests.py`
- Modify: `backend/orders/serializers.py`

**Interfaces:**
- Consumes: `ChannelConnector.fetch() -> list[dict]`, `normalize(raw) -> NormalizedOrder`.
- Produces: `ingest_channel()` counts the raw list before normalization; one normalization error does not suppress valid records; `SyncRun.detail.errors` exposes redacted per-record outcomes.

- [x] **Step 1: Write the malformed-neighbour regression test**

Use a connector whose `fetch()` returns two records and whose second `normalize()` raises `ValueError("malformed quantity")`. Patch `orders.services.get_connector` and assert:

```python
self.assertEqual(run.fetched, 2)
self.assertEqual(run.created, 1)
self.assertEqual(run.failed, 1)
self.assertFalse(run.ok)
self.assertTrue(run.reconciled)
```

Also assert the valid order exists and the serialized run includes an error entry without credentials.

- [x] **Step 2: Run the test and verify RED**

Run `uv run python manage.py test orders.tests.IngestionServiceTests.test_normalization_failure_does_not_drop_valid_neighbour`.

Expected: current code records fetched=0 and failed=0.

- [x] **Step 3: Refactor ingestion around raw-record outcomes**

Keep `fetch()` and `normalize()` separate. `ingest_channel()` obtains `raw_records`, sets `fetched_total = len(raw_records)`, normalizes one record at a time, and accumulates normalization errors identified by index and safe external-ID hints. Extend `ingest_records()` with explicit `fetched_total`, `pre_failed`, and `pre_errors` arguments so its invariant includes normalization failures. A fetch exception remains a channel-level failed run and is distinguishable from record failures.

- [x] **Step 4: Expose safe detail and verify**

Include `detail` in `SyncRunSerializer`. Run `uv run python manage.py test orders` and confirm fixture counts remain 5 Burk raw records and 6 Daraz raw records with one duplicate.

---

### Task 7: Make KPI #3 and Sync Now fail visibly on unavailable or mismatched sources

**Files:**
- Modify: `backend/orders/services.py`
- Modify: `backend/orders/views.py`
- Modify: `backend/orders/serializers.py`
- Modify: `backend/orders/tests.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/app/(app)/orders/page.tsx`

**Interfaces:**
- Consumes: normalized source records, persisted orders/lines, `SyncRun.ok`.
- Produces: queue integrity includes channel errors and field mismatches; Sync Now returns HTTP 207 for partial failure or 503 when every required channel fails; frontend presents partial/failure details.

- [x] **Step 1: Write failing integrity tests**

Add tests proving `queue_integrity()["ok"]` is false when a connector raises, when no channel is successfully inspected, when a persisted total/quantity/status differs, and when a source record is absent locally. Assert `channels_checked` and `channel_errors` values literally.

- [x] **Step 2: Write failing API-response tests**

Patch `sync_all()` to return one successful and one failed run. Assert `/api/orders/sync/` returns 207 and includes `overall_ok: false`. Patch both failed and assert 503. Assert a fully successful sync returns 200.

- [x] **Step 3: Implement canonical reconciliation**

Create focused helpers that canonicalize source and database orders into primitive dictionaries containing source status, currency, subtotal, shipping fee, total, and ordered line tuples `(sku, quantity, unit_price, line_total)`. Compare those structures per source key. Include `channel_errors`, `mismatched_detail`, `channels_checked`, and `required_channels` in the report. `ok` requires all registered required channels checked, zero errors, at least one inspected record, zero dropped/duplicated/mismatched rows, and no stale locally stored key within the connector's authoritative fixture/window.

- [x] **Step 4: Implement truthful API and frontend states**

Return 200/207/503 according to channel results. Extend TypeScript response types with `overall_ok`, run `detail`, and integrity error/mismatch fields. Render failed channels in red and include failed counts in the toast; never show the success sentence when `overall_ok` is false.

- [x] **Step 5: Run Task 7 verification**

Run:

```bash
cd backend
uv run python manage.py test orders
uv run python manage.py check_order_integrity --check
cd ../frontend
npx tsc --noEmit
npm run lint
```

Expected: backend tests and a seeded integrity check pass; frontend type-check/lint have no errors introduced by this task.

---

### Task 8: Eliminate false-positive KPI #2 results

**Files:**
- Modify: `backend/notifications/tests.py`
- Modify: `backend/notifications/services.py`
- Modify: `backend/notifications/management/commands/check_dispatch_latency.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `latency_report(kind, threshold_seconds=180)` and Notification statuses.
- Produces: KPI #2 success requires non-empty sent evidence, zero failures, zero overdue rows, and zero latency breaches.

- [x] **Step 1: Write failing evidence tests**

Add tests asserting `report["ok"] is False` for zero notifications and for two FAILED packaging-video notifications. Assert `evidence_count`, `failed_detail`, and a successful two-channel dispatch. Add command tests proving `check_dispatch_latency --check` exits 1 for zero/failed evidence.

- [x] **Step 2: Run tests and verify RED**

Run `uv run python manage.py test notifications.tests.LatencyReportTests`.

Expected: zero and failed evidence currently report success.

- [x] **Step 3: Implement strict evidence semantics**

Set `evidence_count = len(sent)`, materialize failed rows, and calculate:

```python
ok = evidence_count > 0 and not breaches and not stuck and not failed_rows
```

Return `failed_detail` and print explicit reasons in the command. Keep non-KPI informational reports able to show future scheduled review requests without treating not-yet-due rows as stuck.

- [x] **Step 4: Correct operator documentation**

Remove the inaccurate FYP description from README. Add `--check` to every integrity command that claims a non-zero failure exit. Label fixture connectors and simulated shipment/media/channel actions as development verification, not live platform proof.

- [x] **Step 5: Run Task 8 verification**

Run:

```bash
cd backend
uv run python manage.py test notifications surveillance logistics
uv run python manage.py check_dispatch_latency --check
```

Expected after seeded lifecycle evidence: notification tests and strict KPI command pass; before such evidence, the command intentionally exits non-zero.

---

### Task 9: Gate 1 full regression and acceptance record

**Files:**
- Create: `docs/verification/2026-08-16-core-integrity-results.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all Task 1–8 behavior and migrations.
- Produces: a timestamped evidence record with exact commands, exit codes, test counts, KPI evidence counts, known external blockers, and no unsupported completion claim.

- [x] **Step 1: Apply migrations and seed a disposable PostgreSQL database**

Run:

```bash
cd backend
uv run python manage.py migrate
uv run python manage.py seed_demo --reset
```

The reset is permitted only under the disposable-development guard introduced in the later safety gate; until that gate lands, verify the selected database name and use only the existing local development database.

- [x] **Step 2: Run the complete backend verification**

```bash
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
uv run python manage.py recalculate_stock --check
uv run python manage.py check_order_integrity --check
uv run python manage.py check_pack_integrity --check
uv run python manage.py check_dispatch_latency --check
uv run python manage.py check_shipment_integrity --check
```

Expected: all commands exit 0 only after the acceptance fixture creates real non-empty local evidence for the three KPI checks.

- [x] **Step 3: Run the complete frontend verification**

Add `"typecheck": "tsc --noEmit"` to `frontend/package.json`, then run:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Expected: all exit 0 with no lint errors.

- [x] **Step 4: Run authenticated HTTP and browser acceptance**

Verify Manager and Operator flows: login; inventory adjustment role boundary; reorder/submit/receive; successful and partial-failure sync UI; owner/non-owner packing boundary; mismatch interception; correct scan and pack; one stock decrement; recording/notifications/shipment panels; logout. Record each HTTP status and visible result in the evidence document.

- [x] **Step 5: Record Gate 1 outcome**

Write exact command outputs and identify any unmet row as Failed or External blocker. Mark Gate 1 complete only when every locally controllable Task 1–8 acceptance row is Verified. Do not call the whole system 100% complete at this point; security/operations, real integrations, and production deployment remain later gates from the approved specification.
