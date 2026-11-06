# Reliable Processing, Secure Media, and Observability Plan

> **Execution:** One tracked task at a time, test-first. PostgreSQL is authoritative for `skip_locked` worker concurrency. No Git commit without the user's explicit request.

**Goal:** Complete production Gate 3 by removing external I/O from packing requests, adding a durable leased job/outbox worker, securing and expiring packaging media, and exposing correlation-aware operational health.

**Spec:** `docs/superpowers/specs/2026-08-16-production-completion-design.md`

---

### Task 1: Add a durable leased work queue

**Files:** new `backend/operations/` app, settings/URLs, migrations, tests

- [x] Write PostgreSQL tests proving two workers cannot claim the same due job, expired leases are reclaimable, and enqueue is idempotent by business key.
- [x] Add `WorkItem` (kind, unique key, payload, status, availability, lease, attempts, max attempts, error, completion timestamps) and `WorkerHeartbeat`.
- [x] Implement `enqueue`, `claim_due(select_for_update(skip_locked=True))`, bounded exponential retry, terminal failure, and `run_worker --once/--limit`.
- [x] Run operations tests twice plus migration drift checks.

### Task 2: Convert notifications into a durable idempotent outbox

**Files:** notification model/migration/services/tests/serializers/command

- [x] Add failing idempotency, concurrent-worker, retry-success, terminal-failure, missing-recipient, and overdue tests.
- [x] Add unique business idempotency key, attempt count, next retry, provider message ID, delivery-ack timestamp, and retry/processing statuses.
- [x] Make `dispatch()` persist/enqueue only; send work is claimed by the worker after transaction commit.
- [x] Keep the scheduled-dispatch command as an operational compatibility trigger that drains due notification jobs.
- [x] Make KPI #2 require every configured required channel, successful send acknowledgement, no duplicate key, no pending/retry/failed/late row, and non-empty evidence.

### Task 3: Record from packing start and process after sealing

**Files:** surveillance model/migration/camera interface/services/tests, fulfilment composition

- [x] Add failing tests proving capture starts when the session starts, seals after final verification, and the Complete Pack response performs no FFmpeg/send work.
- [x] Extend camera adapters with health/start/stop/recover; simulated stop generates the deterministic clip.
- [x] Store unrelated random raw/compressed keys, start/stop/seal times, checksums, attempts, and retry state.
- [x] Enqueue compression/dispatch work at sealing; make processing retryable and idempotent.
- [x] Verify a failed FFmpeg attempt later succeeds without another stock decrement or duplicate notification.

### Task 4: Queue shipment booking after pack commit

**Files:** fulfilment view, logistics services/tests, operations handlers

- [x] Add tests proving Complete Pack enqueues one shipment job and returns while the courier adapter is untouched.
- [x] Process booking in the worker; adapter outage retries and terminal failure remain visible instead of pretending shipment automation succeeded.
- [x] Preserve provider/DB idempotency and enqueue tracking notifications only after successful booking commit.

### Task 5: Protect packaging media with authorization and signed links

**Files:** surveillance signing/views/URLs/serializers/tests, config URLs, frontend types

- [x] Add tests: anonymous/no-token denied, bad/expired token denied, valid customer token streams compressed video, owner/Manager staff access succeeds, non-owner Operator denied, raw objects never route.
- [x] Replace direct `/media/` URLs with an authenticated staff endpoint and short-lived signed customer links.
- [x] Ensure notification payloads contain signed compressed links only; production never depends on Django static media serving.

### Task 6: Add auditable media retention cleanup

**Files:** surveillance model/migration/service/command/tests, settings/docs

- [x] Add raw/compressed deletion timestamps and configurable retention periods.
- [x] Implement idempotent cleanup constrained beneath `MEDIA_ROOT`; delete eligible objects, retain database audit rows, and never touch unrelated files.
- [x] Add dry-run/check modes and verify repeated cleanup is safe.

### Task 7: Add correlation IDs, structured logs, and health checks

**Files:** common middleware/logging/health views/tests, operations health/command, settings/URLs

- [x] Add request-correlation middleware that validates/generates an ID, returns it in the response, and makes it available to structured logs.
- [x] Add JSON logging without credentials/raw PII and include relevant model identifiers through explicit log extras.
- [x] Add health components for app, database, worker heartbeat, scheduler backlog, media storage, and configured adapters; unhealthy required components return 503.
- [x] Add `check_operational_health --check` and tests for healthy/stale/degraded states.

### Task 8: Update operator UI for queued/retry/failure states

**Files:** frontend types/resources/packing/order/dashboard pages

- [x] Show recording and shipment as Queued/Processing/Retrying/Failed/Ready without false success.
- [x] Poll boundedly while work is active and expose retryable failure details to Managers.
- [x] Add operational-health evidence counts to the dashboard and keep role restrictions intact.
- [x] Run type-check, lint, production build, and keyboard/browser acceptance.

### Task 9: Gate 3 regression and evidence

**Files:** `docs/verification/2026-08-16-reliable-processing-media-observability-results.md`

- [x] Run the full PostgreSQL suite, repeated worker-concurrency tests, all integrity commands, operational-health check, and migration drift check.
- [x] Run an isolated lifecycle: start capture → scan/seal → HTTP returns queued → worker drains → video ready/signed → notifications sent → shipment booked.
- [x] Run frontend checks and authenticated browser acceptance.
- [x] Record exact evidence and external blockers; do not claim live-complete.
