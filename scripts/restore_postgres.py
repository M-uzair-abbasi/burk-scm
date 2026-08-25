#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys

if __package__:
    from .postgres_utils import connection_info, require_binary, run_checked, sha256_file
else:  # Allow `python scripts/restore_postgres.py` from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.postgres_utils import (  # type: ignore[no-redef]
        connection_info,
        require_binary,
        run_checked,
        sha256_file,
    )


RESTORE_TARGET = re.compile(r"^burk_scm_restore_[a-z0-9_]{3,40}$")
CORE_TABLES = (
    "django_migrations",
    "accounts_user",
    "inventory_product",
    "orders_salesorder",
)


@dataclass(frozen=True)
class RestoreResult:
    database: str
    counts: dict[str, int]
    cleaned_up: bool


def _verify_archive(archive: Path, metadata_path: Path, target: str) -> dict:
    if not archive.is_file() or not metadata_path.is_file():
        raise ValueError("Archive and metadata files are both required.")
    metadata = json.loads(metadata_path.read_text())
    if metadata.get("archive") != archive.name:
        raise ValueError("Metadata does not name this archive.")
    if metadata.get("database") == target:
        raise ValueError("Restore target must differ from the source database.")
    digest = sha256_file(archive)
    if metadata.get("sha256") != digest:
        raise ValueError("Archive checksum does not match metadata.")
    return metadata


def restore_backup(
    archive: Path,
    metadata: Path,
    database_url: str,
    *,
    confirm_target: str,
    replace_existing: bool = False,
    cleanup_after_verify: bool = False,
) -> RestoreResult:
    connection = connection_info(database_url)
    target = connection.database
    if not RESTORE_TARGET.fullmatch(target):
        raise ValueError("Unsafe restore target; use burk_scm_restore_<unique_name>.")
    if confirm_target != target:
        raise ValueError("Exact --confirm-target confirmation is required.")
    _verify_archive(Path(archive), Path(metadata), target)

    createdb = require_binary("createdb", "CREATEDB_BIN")
    pg_restore = require_binary("pg_restore", "PG_RESTORE_BIN")
    psql = require_binary("psql", "PSQL_BIN")
    dropdb = require_binary("dropdb", "DROPDB_BIN")
    admin_environment = {**connection.environment, "PGDATABASE": "postgres"}
    target_environment = {**connection.environment, "PGDATABASE": target}

    if replace_existing:
        run_checked(
            [dropdb, "--if-exists", "--force", target],
            admin_environment,
        )
    run_checked(
        [createdb, "--template=template0", target],
        admin_environment,
    )
    run_checked(
        [
            pg_restore,
            "--exit-on-error",
            "--no-owner",
            "--no-acl",
            f"--dbname={target}",
            str(Path(archive).resolve()),
        ],
        target_environment,
    )

    counts = {}
    for table in CORE_TABLES:
        result = run_checked(
            [
                psql,
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--set=ON_ERROR_STOP=1",
                f"--command=SELECT COUNT(*) FROM {table};",
            ],
            target_environment,
        )
        counts[table] = int(result.stdout.strip())

    if cleanup_after_verify:
        run_checked(
            [dropdb, "--if-exists", "--force", target],
            admin_environment,
        )
    return RestoreResult(
        database=target,
        counts=counts,
        cleaned_up=cleanup_after_verify,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a trusted backup into an isolated drill database.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--confirm-target", required=True)
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--cleanup-after-verify", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    result = restore_backup(
        args.archive,
        args.metadata,
        args.database_url,
        confirm_target=args.confirm_target,
        replace_existing=args.replace_existing,
        cleanup_after_verify=args.cleanup_after_verify,
    )
    print(json.dumps({"database": result.database, "counts": result.counts, "cleaned_up": result.cleaned_up}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
