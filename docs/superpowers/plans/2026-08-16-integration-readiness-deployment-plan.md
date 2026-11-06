# Integration Readiness and Deployment Plan

> **Execution:** One tracked task at a time, test-first. PostgreSQL is
> authoritative. Real-provider calls require approved credentials and are never
> fabricated. No Git commit without the user's explicit request.

**Goal:** Complete every locally controllable requirement in production Gates 4
and 5, leave real-provider/hardware acceptance explicitly blocked, and produce a
truthful final requirement matrix.

**Spec:** `docs/superpowers/specs/2026-08-16-production-completion-design.md`

---

### Task 1: Close Gate 3 review and freeze evidence

- [x] Resolve every valid Critical/Important final-review finding.
- [x] Repeat affected tests and update Gate 3 evidence.
- [x] Mark the reliable-processing plan complete without committing.

### Task 2: Preserve a carrier-ready shipping snapshot

**Files:** order/logistics models, migrations, connector normalization, services,
serializers, tests

- [x] Add structured recipient/address/city/province/postal/country, parcel,
  declared-value/COD/payment/service/pickup/instruction fields without breaking
  historical orders or fixture feeds.
- [x] Persist provider booking ID, request idempotency key, label reference, and
  a redacted provider response on Shipment.
- [x] Build and test one deterministic carrier request contract from the stored
  snapshot; reject unsafe/invalid live payloads before provider I/O.

### Task 3: Add signed, replay-safe courier webhook ingestion

**Files:** logistics models/migration/services/views/URLs/tests/settings

- [x] Add an append-only unique provider-event ledger.
- [x] Verify HMAC signatures with constant-time comparison, reject missing/bad
  signatures, deduplicate replays, resolve shipment safely, redact stored data,
  and enforce forward-only status transitions.
- [x] Keep the Manager-only demo advance endpoint independently gated.

### Task 4: Add provider acknowledgement and safe review-link contracts

**Files:** notifications receipt model/service/view/tests; review-link adapters;
logistics delivery trigger; settings/docs

- [x] Add signed, replay-safe delivery-receipt ingestion that can acknowledge or
  terminally fail a notification by provider message ID.
- [x] Make adapter send results distinguish provider acceptance from delivery
  acknowledgement while preserving deterministic simulated acceptance.
- [x] Generate review destinations through a configured provider using an opaque,
  signed order token; never expose sequential internal `SO-xxxxx` references.

### Task 5: Make external adapter selection configuration-driven

**Files:** order/camera/courier/notification registries, health, settings, env,
contract tests

- [x] Select simulated versus live adapters by environment without source edits.
- [x] Refuse fixture adapters outside demo/test, validate required live settings,
  and expose truthful adapter mode/health without leaking credentials.
- [x] Record Daraz, Burk, camera, courier, WhatsApp, SMTP, and review-destination
  staging acceptance as External blocker until real inputs exist.

### Task 6: Add operational metrics and alert thresholds

**Files:** common metrics service/view/command/tests, dashboard types/resources/UI

- [x] Report queue depth/oldest due/retries/failures, source lag, intercepted pack
  mismatches, notification latency/failures, shipment booking failures, and media
  processing duration using bounded aggregate queries.
- [x] Restrict detailed metrics to Managers, keep health probe public/minimal, and
  add a check command with configurable alert thresholds.
- [x] Add a Manager dashboard panel and verify Operator/API restrictions.

### Task 7: Add reproducible production process packaging

**Files:** backend/frontend Dockerfiles, production compose, reverse-proxy config,
entrypoints, dependency locks, tests/checks

- [x] Build non-root API, worker, and frontend images with pinned dependencies,
  health checks, private media volume, restart policy, and explicit migration job.
- [x] Add reverse-proxy routing/security headers and document TLS termination;
  never expose PostgreSQL or raw media publicly.
- [x] Prove production images/config parse and start where local tooling permits.

### Task 8: Add backup, restore, rollback, and operations drills

**Files:** guarded management/shell utilities, deployment runbook, verification

- [x] Add timestamped PostgreSQL backup with checksum/metadata and a restore drill
  that refuses ambiguous/destructive targets.
- [x] Document migration, static collection, worker rollout, rollback, retention,
  log rotation, monitoring alerts, secret rotation, and incident steps.
- [x] Execute a backup/restore test against an isolated database without touching
  the normal development database.

### Task 9: Add PostgreSQL CI and release gates

**Files:** CI workflow and validation docs

- [x] Run backend tests on PostgreSQL, migration drift/deploy checks, frontend
  typecheck/lint/build, and deterministic integrity acceptance in CI.
- [x] Cache dependencies without caching secrets or generated media.
- [x] Add a release checklist that blocks simulated adapters in live mode.

### Task 10: Final full-system acceptance and requirement matrix

- [x] Run the full PostgreSQL suite, repeated concurrency tests, every integrity,
  retention, health, metrics, deployment, and frontend command.
- [x] Run Manager and Operator browser acceptance across Modules 0–6.
- [x] Publish a module-by-module matrix with Verified / Failed / External blocker /
  Not started, exact evidence, and an honest code-complete/live-complete status.
