# Burk SCM production operations runbook

This runbook covers the application stack in `compose.prod.yml`. It assumes a
trusted operator, a password manager/secret store, PostgreSQL 16 client tools,
and a TLS terminator in front of the loopback-only nginx port. Never paste
production secrets into tickets, logs, shell history, or command arguments.
The release sign-off form is `docs/operations/release-checklist.md`.

## 1. Release preflight

1. Copy `.env.production.example` to an untracked `.env.production`, set mode
   `0600`, replace every placeholder, and obtain staging acceptance for every
   live adapter.
2. Pin one immutable `BURK_SCM_IMAGE_TAG` (release number or Git SHA). Do not
   deploy `latest`.
3. Inject `DATABASE_URL` through the secret store and keep the password URL
   encoded. `POSTGRES_PASSWORD` and the URL password must agree on first boot.
4. Validate before changing processes:

   ```bash
   BURK_SCM_ENV_FILE=.env.production \
     docker compose --env-file .env.production -f compose.prod.yml config --quiet
   cd backend
   uv run python manage.py test
   uv run python manage.py makemigrations --check --dry-run
   env DEBUG=False PRODUCTION_MODE=True SECRET_KEY='<release-check-secret>' \
     ALLOWED_HOSTS=scm.example.com FRONTEND_ORIGIN=https://scm.example.com \
     uv run python manage.py check --deploy --fail-level WARNING
   cd ../frontend && npm ci && npm run typecheck && npm run lint && npm run build
   ```

5. Create and validate a database backup (section 5). Confirm free media and
   backup capacity before a migration.

## 2. Deploy and migrate

The `migrate` service is one-shot. API and worker will not start until it exits
successfully; it also runs `collectstatic`. Never run multiple migration jobs at
once.

```bash
BURK_SCM_ENV_FILE=.env.production \
  docker compose --env-file .env.production -f compose.prod.yml pull
BURK_SCM_ENV_FILE=.env.production \
  docker compose --env-file .env.production -f compose.prod.yml up -d --build
BURK_SCM_ENV_FILE=.env.production \
  docker compose --env-file .env.production -f compose.prod.yml ps
```

Inspect the one-shot result and long-running services:

```bash
docker compose --env-file .env.production -f compose.prod.yml ps -a migrate
docker compose --env-file .env.production -f compose.prod.yml logs --tail=200 migrate api worker frontend proxy
```

Do not use `down -v`; `-v` deletes PostgreSQL and private-media volumes.

## 3. Required schedules

The durable worker is continuous. Two bounded maintenance schedules remain host
or orchestrator jobs so only one scheduler owns each trigger:

- Every 5 minutes: run `python manage.py sync_orders`. Use a host `flock` or the
  orchestrator's `Forbid` concurrency policy so two syncs never overlap. This is
  comfortably inside the default 15-minute source-lag threshold.
- Daily: first run `cleanup_packaging_media --dry-run`, then
  `cleanup_packaging_media`; alert on non-zero/error output.
- Nightly: run the database backup in section 5 and replicate the resulting
  archive + metadata off-host to encrypted storage.
- Weekly: run a restore drill into a fresh `burk_scm_restore_*` target.

Example host scheduler body (lock path is local to the deployment host):

```bash
flock -n /run/lock/burk-scm-sync.lock \
  docker compose --env-file .env.production -f compose.prod.yml \
  exec -T api python manage.py sync_orders
```

## 4. Health, metrics, and alerts

- Anonymous `GET /api/health/` returns only `ok` and `checked_at`.
- Managers can inspect `/api/health/details/` and `/api/metrics/` or the
  dashboard control rail.
- Monitor these commands from inside the API container:

  ```bash
  python manage.py check_operational_health --check
  python manage.py check_operational_metrics --check
  python manage.py recalculate_stock --check
  python manage.py check_order_integrity --check
  python manage.py check_pack_integrity --check
  python manage.py check_dispatch_latency --check
  python manage.py check_shipment_integrity --check
  python manage.py cleanup_packaging_media --check
  ```

Page on stale/missing worker heartbeat, due work older than 180 seconds,
terminal work, missing/late source sync, notification acknowledgement over 180
seconds, dispatch/media/courier failures, stock drift, or KPI/integrity breach.
Tune thresholds by environment only after an owner approves the resulting SLO.

Compose rotates each container's JSON log at 10 MiB and retains five files.
Export logs to the organization's centralized, access-controlled log platform;
the app's JSON formatter redacts common PII/secret forms, but logs must still be
treated as sensitive operational data.

## 5. Database backup

Use PostgreSQL client tools from the same major version as the server. The
script creates a custom-format archive in a mode-0700 directory, validates its
table of contents, computes SHA-256 in bounded chunks, atomically finalizes it,
and writes mode-0600 metadata. Credentials are passed through `PG*` environment
variables, never process arguments.

```bash
# DATABASE_URL is injected into this process by the secret store/service manager.
python3 scripts/backup_postgres.py --output-dir /srv/burk-scm/backups
python3 scripts/prune_backups.py --directory /srv/burk-scm/backups --retention-days 30
# Review the preview, then explicitly apply:
python3 scripts/prune_backups.py --directory /srv/burk-scm/backups --retention-days 30 --apply
```

The newest archive is always preserved by pruning. Copy both `.dump` and `.json`
off-host before pruning. A database dump does not contain packaging videos:
snapshot/encrypt the `private_media` volume separately and retain its checksum
manifest under the same backup-set identifier.

## 6. Isolated restore drill

Only trusted archives generated by this process may be restored: PostgreSQL
archives can execute database code. Restore never targets the live database.
The URL database must match `burk_scm_restore_<unique_name>` and
`--confirm-target` must repeat it exactly.

```bash
# DATABASE_URL is injected and names burk_scm_restore_20260817.
python3 scripts/restore_postgres.py \
  --archive /srv/burk-scm/backups/burk-scm_burk_scm_TIMESTAMP.dump \
  --metadata /srv/burk-scm/backups/burk-scm_burk_scm_TIMESTAMP.json \
  --confirm-target burk_scm_restore_20260817
```

Inspect the reported migration/user/product/order counts and run Django
integrity commands against the restored URL. Only then remove the scratch DB:

```bash
python3 scripts/restore_postgres.py ... \
  --confirm-target burk_scm_restore_20260817 \
  --replace-existing --cleanup-after-verify
```

`--replace-existing` and cleanup can affect only the strict restore prefix. If
a restore fails, the partial scratch database is deliberately retained for
diagnosis; use `dropdb --force` only after resolving and retyping its exact name.

## 7. Rollback

1. Stop new warehouse writes at the trusted edge and let in-flight worker jobs
   finish or expire their leases.
2. Capture DB and media backups before rollback.
3. If the migration is backward-compatible, redeploy the previous immutable
   image tag without reversing migrations, then run health/integrity checks.
4. Never run a reverse migration blindly. For an incompatible schema/data
   change, restore the pre-release backup into an isolated database, verify it,
   obtain owner approval for a maintenance-window cutover, and preserve the
   failed database until incident closure.
5. Re-enable traffic only after Manager and Operator smoke tests and all
   integrity gates pass.

## 8. Secret rotation

Rotate one dependency at a time: database password/URL, Django `SECRET_KEY`,
Daraz/Burk tokens, camera credentials, courier keys/webhook secret, WhatsApp
token/webhook secret, SMTP credentials, and review token. Update the secret
store, recreate only affected services, verify adapter health and one staging
transaction, then revoke the old credential. Rotating Django `SECRET_KEY`
invalidates sessions and signed customer links; schedule and communicate it.
Never print the detailed health environment or Compose-expanded environment in
shared logs.

## 9. Incident response

1. Declare the incident, timestamp it, assign an incident lead, and pause risky
   writes/provider retries if they can amplify harm.
2. Preserve app/proxy/worker logs, correlation IDs, WorkItem/SyncRun/scan/
   notification/shipment ledgers, and current DB/media snapshots.
3. Classify: security/credential, data integrity, provider outage, queue/worker,
   media/storage, or deployment regression.
4. Contain: revoke leaked credentials, block bad webhook signatures, stop only
   the affected worker kind/integration, or roll back using section 7.
5. Recover and run every applicable health/KPI/integrity check plus Manager and
   Operator smoke acceptance.
6. Record timeline, customer impact, root cause, corrective action, owner, and
   recurrence test. Do not delete append-only audit evidence to make checks pass.
