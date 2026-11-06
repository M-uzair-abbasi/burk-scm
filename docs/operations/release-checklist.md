# Burk SCM release checklist

A release is blocked until every applicable box is checked by its named owner.
CI proves internal software/configuration contracts; it never substitutes dummy
values for external staging acceptance.

## Automated gate

- [ ] GitHub Actions `CI / verify` is green on the exact immutable release SHA.
      Blocked: nothing has been pushed to `origin/main` yet, so this has
      literally never run. Everything below is proven locally instead — see
      `docs/verification/2026-09-28-completion-pass-results.md`.
- [x] Full PostgreSQL suite and three repeated concurrency passes are green.
      226 tests OK; 15/15 concurrency executions across 3 runs (2026-09-28).
- [x] No migration drift; uv/npm locks are unchanged and frozen installs pass.
      `makemigrations --check` clean, `uv lock --check` clean, `npm ci` clean
      (2026-09-28).
- [ ] Production Django deploy check and `check_release_policy` pass.
      `check --deploy` passes (0 issues); `check_release_policy` correctly
      still refuses (32 violations, all external-credential blockers below —
      this is the gate working as intended, not a bug).
- [x] Deterministic integrity/health/metrics commands pass.
      All seven commands OK against a real driven pack→ship→deliver→review
      cycle (2026-09-28).
- [x] Frontend typecheck, lint, production/standalone build pass.
      Also: `npm audit` fixed from 5 vulnerabilities (1 critical) to 0
      (2026-09-28).
- [x] Production Compose config and both image builds pass.
      Both images now actually built and smoke-tested for the first time —
      previously blocked on docker group membership (2026-09-28).

## External acceptance (never inferred from CI)

- [ ] Daraz staging pull, pagination, status mapping, rate limits, and idempotent replay accepted.
- [ ] Burk authoritative order contract and representative staging replay accepted.
- [ ] Warehouse camera framing, reconnect, duration, FFmpeg output, and retention accepted.
- [ ] Courier sandbox booking/label and signed duplicate/out-of-order webhooks accepted.
- [ ] WhatsApp approved templates/send/accepted/delivered/failed receipts accepted.
- [ ] SMTP sender/domain, inbox delivery, bounce handling, and redaction accepted.
- [ ] Burk review destination/token redemption and expiry accepted.

Any `fixture`, `simulated`, console/locmem/dummy email, placeholder setting, or
`REQUIRE_LIVE_INTEGRATIONS=False` blocks a live release.

## Operational approval

- [ ] Immutable image tag and rollback tag recorded.
- [ ] Current DB backup plus checksum/metadata copied to encrypted off-host storage.
      Backup + SHA-256 checksum + restore drill itself succeeded fresh on
      2026-09-28 (see verification doc) — left unchecked because the archive
      only exists locally; "encrypted off-host storage" needs a real target.
- [ ] Most recent isolated restore drill is successful and within approved RTO/RPO.
      The drill succeeded (43 migrations/2 users/9 products/10 orders,
      matched the live source exactly) — left unchecked because no RTO/RPO
      has actually been approved by a release owner to measure against.
- [ ] Private-media snapshot/manifest complete.
- [ ] Migration reviewed for backward compatibility and maintenance needs.
- [ ] Five-minute order sync, durable worker, nightly backup, daily media cleanup,
      and monitoring schedules are enabled with non-overlap controls.
- [ ] TLS/DNS, loopback edge binding, firewall, centralized logs, alerts, and on-call are ready.
- [ ] Secret owner confirms production credentials are in the secret store and old credentials have a rotation plan.
- [ ] Manager and Operator staging browser acceptance passed.
- [ ] Release owner gives explicit go/no-go approval.
