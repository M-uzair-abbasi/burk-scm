# Final acceptance and requirement matrix — 2026-08-17

## Verdict

The application implements all seven planned software workflows (foundation plus
Modules 1–6) and the complete local/demo path is verified. It is **not yet a live
production rollout**: real Daraz, Burk, camera, courier, WhatsApp, SMTP, and review
provider access was not supplied, so those integrations remain fail-closed behind
environment-selected live adapters and the production release gate.

Completion must therefore be reported in two dimensions:

- **Implemented workflows:** 7/7 (100%).
- **Locally controllable acceptance:** complete; all automated, database,
  browser, KPI, build, security, backup/restore, and configuration gates below
  passed.
- **Live external integrations accepted:** 0/7. Credentials, contracts,
  hardware, and vendor staging environments are external blockers; no live
  success was fabricated.

## Module acceptance

| Scope | Source requirement | Internal status and evidence | Live status |
| --- | --- | --- | --- |
| Foundation | PostgreSQL setup, authentication, role-aware dashboard | **Verified.** Manager and Operator logins rendered successfully. Manager received operational health/metrics; Operator navigation excluded Suppliers and Purchase Orders and `/api/metrics/` returned HTTP 403. | Deployment configuration is ready; hosted deployment remains an operational action. |
| Module 1 | Inventory alerts, suppliers, reorder and purchase workflow | **Verified.** Browser acceptance recorded an append-only stock adjustment, selected the preferred supplier/tier, created PO-00006, submitted it, and received 50 units. Final ledger check: 9/9 products, zero drift. | No external dependency. |
| Module 2 | Burk + Daraz aggregation with no dropped/duplicated records | **Verified internally.** A browser-triggered re-sync reported 0 new, 10 updated, 1 duplicate skipped; the queue stayed at 10 unique orders. Final command: `0 dropped, 0 duplicated, 10 unique orders`. | **External blocker.** Live Daraz credentials and the authoritative Burk order API/DB contract are absent. `live_daraz.py` and `live_burk.py` intentionally refuse to pretend otherwise. |
| Module 3 | Scanner matching with 100% visible/audible mismatch interception | **Verified internally.** One wrong barcode was recorded as `mismatch`, left progress at 0/1, and never counted as packed; the correct barcode advanced to 1/1. Final command verified 2 scans, 1 intercepted mismatch, 0 mismatches counted as packed, and 1 completed pack. | Physical keyboard-wedge scanner, warehouse display, and speaker acceptance require the real workstation hardware. |
| Module 4 | Per-order packaging recording, FFmpeg compression, Email + WhatsApp dispatch within 3 minutes | **Verified internally.** The real FFmpeg pipeline produced a 3-second, 34 KB clip. Email and WhatsApp were both acknowledged in 1.2 seconds. Final KPI command: 2 video notifications sent, max latency 1.2 seconds, 0 failed/overdue. | **External blocker.** Real overhead/RTSP camera, approved WhatsApp sender/templates, SMTP sender/domain, and delivery receipts require vendor/hardware access. |
| Module 5 | Automatic courier booking and customer tracking distribution | **Verified internally.** Completing the pack durably booked M&P without manual AWB entry, generated tracking ID `MNP81BE74619AC7C1D7`, and advanced Booked → In transit → Delivered. Email and WhatsApp tracking notices were acknowledged in 0.1/0.2 seconds. | **External blocker.** Courier sandbox credentials, booking/label contract, and signed staging webhooks are absent. |
| Module 6 | Delivery-triggered review reminder through Email + WhatsApp | **Verified internally.** Delivery created two one-minute delayed jobs; the continuously running worker sent Email and WhatsApp reminders at 60.4/60.5 seconds with zero failure/overdue rows. | **External blocker.** The real Burk review destination/token contract and live messaging channels are absent. |

## Estimate traceability (334-hour workbook)

| Estimate group | Hours | Acceptance result |
| --- | ---: | --- |
| Foundation: setup/database plus login/dashboard | 16 | Verified locally. |
| Module 1: stock alerts, suppliers/reorder, UI | 19 | Verified locally, including a complete PO receipt loop. |
| Module 2: Burk pull, Daraz API, deduplication, queue UI | 50 | Aggregation/deduplication/UI verified; both real source contracts are external blockers. |
| Module 3: scanner, matching, flash/sound, testing | 35 | Software path verified; physical-device acceptance is external. |
| Module 4: camera, FFmpeg, send/testing | 68 | FFmpeg and durable two-channel workflow verified; live camera/providers are external. |
| Module 5: courier booking and tracking distribution | 50 | Durable workflow/webhooks verified; live courier staging is external. |
| Module 6: delivery/review trigger | 10 | Scheduler/worker/two-channel workflow verified; live destination/providers are external. |
| Final setup/testing/deployment/documentation | 50 | Test, runbook, release, backup/restore, Compose, Gunicorn, and frontend gates verified. Live messaging setup, hosted CI, and deployment require external access. |
| Contingency | 36 | Planning allowance, not a functional requirement. |

## Fresh acceptance evidence

### Backend and database

- PostgreSQL full suite: **224 tests passed**, 0 failures, exit 0, 263.848s.
- Concurrency gate: five PostgreSQL race tests passed in each of three runs
  (15/15 executions).
- Migrations: current; `makemigrations --check --dry-run` reported no changes.
- Upgrade regression: `notifications.0004_backfill_notification_jobs` now
  creates durable jobs for active legacy notification rows. Its test was seen
  fail before the migration existed and pass afterward; the live upgrade
  backfilled and sent the two previously orphaned review reminders.
- Stock ledger: 9/9 products agree with the append-only movement ledger.
- Order queue: 0 dropped, 0 duplicated, 10 unique.
- Packing: 2 scans, 1 mismatch intercepted, 0 mismatches packed, 1 complete pack.
- Shipments: 1/1 completed-pack shipment automatically booked.
- Notifications: 6/6 acknowledged; video max 1.2s, tracking max 0.2s,
  review max 60.5s; 0 failed/overdue.
- Health/metrics: worker current, queue due 0, failed 0, processing 0; no
  threshold breaches; media retention clean.

### Frontend and dependencies

- Locked clean install: `npm ci` passed.
- Security audit: **0 vulnerabilities** after updating Next.js and
  `eslint-config-next` to 16.3.1 and applying compatible transitive patches.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm run build`: passed on Next.js 16.3.1; all 13 application routes built and
  `.next/standalone/server.js` exists.
- Manager and Operator browser journeys passed against the production frontend
  and current Django source.

### Deployment and operations

- `uv sync --frozen`, `uv lock --check`, Python compile, Django system check,
  production `check --deploy`, release policy, Gunicorn config, and production
  Compose config all passed.
- PostgreSQL 16 restore drill restored 42 migrations, 2 users, 9 products, and
  10 orders into an isolated scratch database, verified checksums/counts, and
  removed only the scratch target.
- Local Docker image execution was not run because this OS user cannot access
  `/var/run/docker.sock`. Both image builds are release gates in the SHA-pinned
  GitHub Actions workflow, whose first hosted run requires the user to commit
  and push the working tree.

## External blockers before a truthful live-release claim

1. Daraz Seller Center staging app key, secret, access token, endpoint contract,
   pagination/rate-limit samples, and representative payloads.
2. Burk authoritative order and review API/DB/webhook contracts plus staging
   credentials.
3. Warehouse camera source/device and physical scanner/display/speaker hardware.
4. Courier sandbox credentials, label/booking samples, and webhook secrets.
5. WhatsApp Business approved templates/sender token and delivery webhook.
6. SMTP credentials, verified sender/domain, bounce path, and inbox acceptance.
7. Production secret store, DNS/TLS, monitoring/on-call, off-host backup target,
   Docker-enabled deployment host, and release-owner approval.

Until those are supplied and the release checklist passes against their real
staging environments, the honest status is **software-complete and locally
verified, externally blocked from live completion**.
