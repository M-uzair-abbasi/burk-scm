# Burk SCM release checklist

A release is blocked until every applicable box is checked by its named owner.
CI proves internal software/configuration contracts; it never substitutes dummy
values for external staging acceptance.

## Automated gate

- [ ] GitHub Actions `CI / verify` is green on the exact immutable release SHA.
- [ ] Full PostgreSQL suite and three repeated concurrency passes are green.
- [ ] No migration drift; uv/npm locks are unchanged and frozen installs pass.
- [ ] Production Django deploy check and `check_release_policy` pass.
- [ ] Deterministic integrity/health/metrics commands pass.
- [ ] Frontend typecheck, lint, production/standalone build pass.
- [ ] Production Compose config and both image builds pass.

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
- [ ] Most recent isolated restore drill is successful and within approved RTO/RPO.
- [ ] Private-media snapshot/manifest complete.
- [ ] Migration reviewed for backward compatibility and maintenance needs.
- [ ] Five-minute order sync, durable worker, nightly backup, daily media cleanup,
      and monitoring schedules are enabled with non-overlap controls.
- [ ] TLS/DNS, loopback edge binding, firewall, centralized logs, alerts, and on-call are ready.
- [ ] Secret owner confirms production credentials are in the secret store and old credentials have a rotation plan.
- [ ] Manager and Operator staging browser acceptance passed.
- [ ] Release owner gives explicit go/no-go approval.
