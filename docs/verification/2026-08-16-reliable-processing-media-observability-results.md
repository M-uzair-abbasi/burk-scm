# Reliable Processing, Secure Media, and Observability — Verification Results

**Date:** 2026-08-16  
**Branch:** `codex/production-completion`  
**Scope:** Production-completion Gate 3

## Outcome

Gate 3 passes for all locally controllable requirements. External I/O is outside
the packing request, durable work is leased and retryable, notifications are an
idempotent outbox, customer media is protected, retention is auditable, and the
application exposes truthful operational health.

This is code/demo acceptance with simulated channel, camera, courier, and
WhatsApp adapters plus the Django development email backend. It is not live
provider acceptance; credentials, contracts, infrastructure, and physical
hardware remain deployment-owner inputs.

## Authoritative regression

Run against PostgreSQL 16 on host port 5433:

```bash
cd backend
uv run python manage.py test --verbosity 1
```

Result: **180 tests passed in 248.362 seconds**. The suite includes authorization,
atomic rollback, queue retries, terminal failures, lease recovery, outbox
idempotency, recording recovery, signed media, HTTP range streaming, retention,
correlation logging, operational health, and every earlier module regression.

The three PostgreSQL concurrency classes were then run together twice,
sequentially:

```bash
uv run python manage.py test \
  operations.tests.ConcurrentClaimTests \
  inventory.tests.ConcurrentMovementTests \
  purchasing.tests.ConcurrentReceiptTests
```

Both passes completed **3/3 OK**. They prove two workers do not claim one job,
concurrent stock movements do not lose updates, and concurrent PO receipts do
not double-receive stock.

Static/schema checks:

```bash
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

Result: no system-check issues and no migration drift. The normal local database
was also brought forward through all nine pending Gate 1–3 migrations; no demo
reset was performed.

The strict production profile was rechecked with HTTPS origins, a high-entropy
environment secret, every demo switch off, and live-adapter enforcement on:

```bash
uv run python manage.py check --deploy --fail-level WARNING
```

Result: no deployment-check warnings.

Frontend checks:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Result: TypeScript, ESLint, and the Next.js 16 production build all passed; all
application routes were generated successfully.

## Isolated lifecycle acceptance

Browser and integrity acceptance used the isolated database
`burk_gate3_accept_20260816_1716` and media root
`/tmp/burk-gate3-media-20260816-1716`. Migrations and demo seed created 9
products, 3 suppliers, and 10 unified orders without touching normal demo data.

The Manager exercised `SO-00001` through this lifecycle:

1. Start packing. The recording lifecycle starts with the packing session.
2. Scan barcode `8964000000046`; the one required line changes from 0/1 to 1/1.
3. Stop the worker and click **Complete pack**.
4. The HTTP response succeeds immediately and visibly reports **Queued for
   processing** plus **Courier booking queued**. No video/courier/provider work
   can have completed while the worker is stopped.
5. Restart the worker. The UI progresses automatically to a ready 3-second,
   34-KB compressed video, two acknowledged packaging notifications, and one
   booked simulated TCS shipment.
6. The protected video element loads from `/api/recordings/1/video/` with
   `readyState=4`, duration 3 seconds, and no playback error.
7. Advance the shipment to In transit and Delivered. Two review reminders are
   shown as Scheduled, then the continuously running worker sends both when due
   without a manual scheduler command.

Observed browser evidence:

- Packaging video: Email and WhatsApp both **Sent in 8.2s**.
- Shipment tracking: Email and WhatsApp both acknowledged in **0.2s**.
- Review request: Email and WhatsApp both automatically sent in **60.1s**.
- Dashboard: **Ready**, live worker heartbeat, 0 due jobs, 0 failed jobs, 6/6
  adapters available.
- Browser warning/error log: **0 entries**.

## Integrity, KPI, retention, and health commands

All commands exited 0 against the isolated lifecycle database:

```bash
uv run python manage.py recalculate_stock --check
uv run python manage.py check_order_integrity --check
uv run python manage.py check_pack_integrity --check
uv run python manage.py check_dispatch_latency --check
uv run python manage.py check_shipment_integrity --check
uv run python manage.py cleanup_packaging_media --check
uv run python manage.py check_operational_health --check
```

Exact results:

- Stock: 9 products agree with the append-only ledger; zero drift.
- Orders/KPI #3: 0 dropped, 0 duplicated, 10 unique; queue integrity OK.
- Packing/KPI #1: 1 completed pack, 1 accepted scan, 0 mismatches counted as
  packed; packing integrity OK.
- Packaging/KPI #2: 2 acknowledged sends, max 8.2s, 0 failed, 0 overdue, all
  required channels present, all below 180s.
- Shipment: 1 automatically booked shipment; no manual gap.
- Retention: 0 due, 0 unsafe, no unrelated object touched; policy clean.
- Health: app, database, worker, backlog, media, and all configured adapters
  healthy; 0 due/failed/processing work.

## Security and reliability behavior covered

- Complete Pack performs only transactional state changes and durable enqueue;
  no FFmpeg, notification-provider, or courier call runs inline.
- Business-key uniqueness prevents duplicate recording, shipment, and
  notification jobs; provider booking receives a stable idempotency key.
- Leased PostgreSQL claims use `skip_locked`, expired work is reclaimable, retry
  is bounded, and terminal failure is visible to Managers.
- Anonymous video access needs a valid, unexpired checksum-bound token. Manager
  and session-owner access is authorized; another Operator is denied.
- Raw clips and `/media/` are not routed. Traversal, symlinks, checksum mismatch,
  and expired/bad tokens are rejected; compressed video supports HTTP 206 range
  responses.
- Raw/compressed retention periods are independently configurable and cleanup is
  constrained below `MEDIA_ROOT`, repeat-idempotent, and audit-row preserving.
- Request IDs are validated/generated, echoed to callers, propagated into work
  items, and emitted in JSON logs with PII/secret redaction.
- Production readiness can require live adapters; with
  `REQUIRE_LIVE_INTEGRATIONS=True`, any simulated adapter makes health fail
  instead of falsely reporting live readiness.

Post-review hardening added two focused regressions: `process_due(limit>1)` now
leases each row only immediately before its handler starts (later rows no longer
lose lease time behind a slow first job), and authorized streaming rejects every
symlink path even when its target remains inside `MEDIA_ROOT`. The complete
operations + surveillance set then passed **33/33 tests in 74.182 seconds**.

## External rollout blockers

No internal Gate 3 implementation remains. Live rollout still requires Daraz
and Burk order access, camera hardware/stream details, courier credentials and
webhook contract, approved WhatsApp templates/token, real SMTP credentials,
private production media storage, process supervision, TLS/reverse proxy, and
staging acceptance. These were not fabricated or marked complete.
