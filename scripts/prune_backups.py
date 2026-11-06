#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

if __package__:
    from .postgres_utils import safe_directory
else:  # Allow `python scripts/prune_backups.py` from the repository root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.postgres_utils import safe_directory  # type: ignore[no-redef]


def _age_days(path: Path) -> float:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - modified).total_seconds() / 86_400


def prune(directory: Path, *, retention_days: int, apply: bool = False) -> list[Path]:
    if retention_days < 1:
        raise ValueError("retention_days must be at least one day.")
    root = safe_directory(Path(directory))
    archives = sorted(root.glob("burk-scm_*.dump"), key=lambda path: path.stat().st_mtime)
    if len(archives) < 2:
        return []
    newest = archives[-1]
    candidates = [
        archive
        for archive in archives
        if archive != newest and not archive.is_symlink() and _age_days(archive) > retention_days
    ]
    if apply:
        for archive in candidates:
            metadata = archive.with_suffix(".json")
            archive.unlink()
            metadata.unlink(missing_ok=True)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or apply Burk SCM backup retention.")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    candidates = prune(args.directory, retention_days=args.retention_days, apply=args.apply)
    action = "deleted" if args.apply else "would delete"
    for candidate in candidates:
        print(f"{action}: {candidate}")
    print(f"{len(candidates)} backup(s) {action}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
