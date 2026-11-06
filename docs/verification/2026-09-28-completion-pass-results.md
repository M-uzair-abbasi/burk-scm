# Completion pass — 2026-09-28

Follow-up to the 2026-08-17 final acceptance matrix, after the UI/UX redesign
(2026-09-21) had sat uncommitted for five weeks. This pass: (1) re-verified
every claim in that matrix still holds against current source, (2) found and
fixed two real regressions introduced since then, (3) closed every previously
blocked local verification gap that didn't require external vendor access.

## What was found and fixed

**Notification bug (real, reproducible):** `orders.connectors.daraz.normalize()`
correctly sets `customer_email=""` for every Daraz order — Daraz's real Seller
Center API never exposes the buyer's email to sellers, only phone/address, so
this is accurate modelling, not a bug. But `notifications.services.dispatch()`
still created an EMAIL `Notification`/`WorkItem` for that empty recipient
anyway, which `process_notification_work` then permanently failed with
`"Order has no customer_email on file."` — a manufactured failure for a
channel the order could never reach, visible as a permanently-failed row and
an amber operational-health lamp on every Daraz pack.

Fix: `dispatch()` now skips creating a row for a channel the order has no
recipient for. `latency_report()`'s `PACKAGING_VIDEO` "required channels"
check was updated to mean "required among channels this order can actually
reach," not "always both, unconditionally" — so a Daraz order is only ever
held to a WhatsApp-only bar, not an impossible email bar. Two tests updated
(`test_missing_recipient_fails_that_channel_without_raising` →
`test_missing_recipient_skips_that_channel_without_raising`,
`test_report_fails_when_required_channels_failed` rewritten to exercise a
genuine provider failure via a mocked channel instead of a missing recipient)
plus one new test (`test_dispatch_with_no_reachable_channels_creates_nothing`).
Verified against real seeded data, not just the test fixtures: dispatching a
`PACKAGING_VIDEO` notification for a real Daraz order now creates exactly one
row (WhatsApp), it sends, and `latency_report` reports `ok=True` with no
missing required channels.

**Frontend dependency vulnerabilities (real regression):** the UI redesign's
new dependencies (`lucide-react`, `clsx`, `@radix-ui/react-*`) pulled in a
transitive dependency tree with 5 known vulnerabilities, including a
**critical unauthenticated RCE in Next.js 16.0.0–16.3.2** (fixed upstream in
16.3.6). `npm audit fix --force` resolved all 5 (`next` → `16.3.6`); re-ran
typecheck, lint, and a full production build afterward — all clean, all 13
routes still build. `npm audit`: **0 vulnerabilities**.

## Fresh evidence — backend

- Full suite: **226 tests, `OK`** (225 from the 2026-08-17 baseline, +1 net
  from the notification-fix test changes above).
- Concurrency gate re-run **3 times** (not reused from before): the same five
  `TransactionTestCase` race tests (`inventory.ConcurrentMovementTests`,
  `operations.ConcurrentClaimTests`, `purchasing.ConcurrentReceiptTests`,
  `fulfillment.ConcurrentPackingCompletionTests`,
  `logistics.ConcurrentCourierWebhookTests`) — **15/15 passed**.
- `makemigrations --check --dry-run`: no changes. `uv lock --check`: resolved
  clean.
- `manage.py check --deploy --fail-level WARNING` under a prod-shaped
  environment (`DEBUG=False`, `PRODUCTION_MODE=True`, strong `SECRET_KEY`,
  real-looking hosts/origins): **0 issues**.
- `check_release_policy` **correctly still refuses** to certify a release —
  32 violations, all of them the expected fixture/simulated-adapter and
  missing-live-credential blockers (Daraz/Burk/camera/courier/WhatsApp/SMTP
  keys, webhook secrets). This is the gate working as designed, not a defect;
  it will only pass once the external acceptance items below are met.
- Drove one full real order (`SO-00236`, Burk channel) through the entire
  pack → video → ship → deliver → review chain via the real service layer
  (mirroring `fulfillment.views.PackingViewSet` exactly, not a shortcut).
  Result: packaging-video and shipment-tracking notifications sent on both
  channels, real tracking number booked (`LCS7AD3DA0B1D83F5D1`), review
  reminder scheduled and auto-sent by the durable worker with zero manual
  steps.
- Integrity/health/metrics commands, all green against that live state:
  `recalculate_stock --check` (no drift, 9/9 products),
  `check_order_integrity --check` (0 dropped, 0 duplicated, 10 unique),
  `check_pack_integrity --check` (0 mismatches counted as packed, 1 completed
  pack verified), `check_shipment_integrity --check` (1/1 automatically
  booked), `check_dispatch_latency --check`, `check_operational_health
  --check`, `check_operational_metrics --check` — all OK, zero breaches.

## Fresh evidence — frontend

- `npm ci`: clean. `npm audit`: 0 vulnerabilities (post-fix).
- `npm run typecheck`, `npm run lint`, `npm run build`: all pass; all 13
  application routes build (`.next/standalone/server.js` present).

## Fresh evidence — deployment (previously blocked, now closed)

The 2026-08-17 matrix explicitly noted: *"Local Docker image execution was
not run because this OS user cannot access `/var/run/docker.sock`."* That
blocker is gone (the user is now in the `docker` group) and both images were
actually built and smoke-tested for the first time:

- `docker build -f backend/Dockerfile` — succeeds; `python manage.py check`
  inside the built image: 0 issues.
- `docker build -f frontend/Dockerfile` — succeeds; container started and
  served `HTTP 200` on `/login`.
- `docker compose -f compose.prod.yml config --quiet` against
  `.env.production.example`: valid.
- Backup/restore drill re-run fresh (not reused from 2026-08-17): real
  `pg_dump` custom-format archive (via a `postgres:16` client matched to the
  server version — this host still has no local PostgreSQL client installed),
  validated with `pg_restore --list`, SHA-256 checksum recorded, restored
  into a disposable scratch database (`burk_scm_restore_verify_*`), row
  counts cross-checked against the live source
  (43 migrations / 2 users / 9 products / 10 orders — exact match both sides),
  scratch database dropped and confirmed gone afterward.

## What's still genuinely open

- **GitHub Actions CI has still never run.** `origin/main` remains at the old
  `79af6b8` commit; nothing from the 2026-08-17 production-completion layer
  or the 2026-09-21 UI redesign has been pushed. This is the actual remaining
  risk — all of the above is proven locally, on one machine, with no remote
  backup.
- **External acceptance: still 0/7**, unchanged from 2026-08-17 — Daraz
  Seller Center, Burk's authoritative order/review contract, warehouse
  camera/scanner hardware, courier sandbox, WhatsApp Business API, SMTP
  sender, and a real hosting target with DNS/TLS. None of this is a code gap;
  `check_release_policy` names every missing credential explicitly and
  refuses to let a simulated setup masquerade as live.
- **Operational-approval items that assume a real deployment target**
  (off-host encrypted backup storage, DNS/TLS, monitoring/on-call, secret
  rotation) remain open for the same reason — there is no production host to
  point them at yet.
