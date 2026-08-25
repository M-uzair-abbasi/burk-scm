# PostgreSQL backup/restore drill — 2026-08-17

Result: **Verified** against the running PostgreSQL development server without
writing to the normal `burk_scm` database.

- Client: PostgreSQL 16.14, extracted into a disposable `/tmp` directory with no
  sudo/system-package change.
- Backup format: custom, validated by `pg_restore --list`.
- Archive: mode `0600`, 141,253 bytes.
- SHA-256: `b50748309b894b9edd597ae28bb58865d4a884434ce63c4be8c1a422c3ef50aa`.
- Exact scratch target: `burk_scm_restore_codex_20260817`.
- Restored evidence: 42 migrations, 2 users, 9 products, 10 sales orders.
- Cleanup: the strict scratch target was explicitly removed after verification;
  a catalog query confirmed zero databases with that exact name.
- Source recheck: normal database still had 2 users, 9 products, 10 orders.

The drill artifacts remain only in the disposable path
`/tmp/burk-scm-restore-drill.PMfuTV`; they are verification data, not a retained
production backup.
