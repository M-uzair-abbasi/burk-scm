#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys

if __package__:
    from .postgres_utils import (
        connection_info,
        require_binary,
        run_checked,
        safe_directory,
        sha256_file,
    )
else:  # Allow `python scripts/backup_postgres.py` from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.postgres_utils import (  # type: ignore[no-redef]
        connection_info,
        require_binary,
        run_checked,
        safe_directory,
        sha256_file,
    )


@dataclass(frozen=True)
class BackupResult:
    archive: Path
    metadata: Path


def create_backup(database_url: str, output_dir: Path) -> BackupResult:
    connection = connection_info(database_url)
    output_dir = safe_directory(Path(output_dir))
    pg_dump = require_binary("pg_dump", "PG_DUMP_BIN")
    pg_restore = require_binary("pg_restore", "PG_RESTORE_BIN")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    basename = f"burk-scm_{connection.database}_{stamp}_{secrets.token_hex(3)}"
    archive = output_dir / f"{basename}.dump"
    partial = output_dir / f".{basename}.dump.partial"
    metadata = output_dir / f"{basename}.json"
    metadata_partial = output_dir / f".{basename}.json.partial"

    try:
        run_checked(
            [
                pg_dump,
                "--format=custom",
                "--compress=6",
                "--no-owner",
                "--no-acl",
                f"--file={partial}",
            ],
            connection.environment,
        )
        if not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError("pg_dump produced no archive data.")
        run_checked(
            [pg_restore, "--list", str(partial)],
            connection.environment,
        )
        digest = sha256_file(partial)
        size = partial.stat().st_size
        os.replace(partial, archive)
        archive.chmod(0o600)
        payload = {
            "archive": archive.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": connection.database,
            "format": "postgresql-custom",
            "sha256": digest,
            "size_bytes": size,
        }
        metadata_partial.write_text(json.dumps(payload, indent=2) + "\n")
        metadata_partial.chmod(0o600)
        os.replace(metadata_partial, metadata)
        return BackupResult(archive=archive, metadata=metadata)
    except Exception:
        partial.unlink(missing_ok=True)
        metadata_partial.unlink(missing_ok=True)
        if archive.exists() and not metadata.exists():
            archive.unlink()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a verified Burk SCM PostgreSQL backup.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    result = create_backup(args.database_url, args.output_dir)
    print(json.dumps({"archive": str(result.archive), "metadata": str(result.metadata)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
