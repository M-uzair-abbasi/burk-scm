from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import parse_qs, unquote, urlparse


@dataclass(frozen=True)
class ConnectionInfo:
    database: str
    environment: dict[str, str]


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connection_info(database_url: str) -> ConnectionInfo:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use postgres:// or postgresql://.")
    if not parsed.hostname or parsed.username is None:
        raise ValueError("DATABASE_URL must include a host and user.")
    database = unquote(parsed.path.lstrip("/"))
    if not database or "/" in database:
        raise ValueError("DATABASE_URL must identify exactly one database.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,62}", database):
        raise ValueError("DATABASE_URL contains an unsafe database name.")

    environment = os.environ.copy()
    for name in (
        "DATABASE_URL",
        "PGDATABASE",
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "PGSERVICE",
        "PGPASSFILE",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "PGDATABASE": database,
            "PGHOST": parsed.hostname,
            "PGPORT": str(parsed.port or 5432),
            "PGUSER": unquote(parsed.username),
            "PGPASSWORD": unquote(parsed.password or ""),
        }
    )
    query = parse_qs(parsed.query)
    if query.get("sslmode"):
        environment["PGSSLMODE"] = query["sslmode"][-1]
    return ConnectionInfo(database=database, environment=environment)


def require_binary(name: str, override_variable: str) -> str:
    configured = os.environ.get(override_variable, "").strip()
    path = configured or shutil.which(name)
    if not path:
        raise RuntimeError(
            f"{name} is required; install PostgreSQL client tools or set "
            f"{override_variable}."
        )
    return path


def run_checked(command: list[str], environment: dict[str, str]):
    result = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "no diagnostic").strip()
        detail = re.sub(r"(?i)(password|token|secret)=\S+", r"\1=[redacted]", detail)
        raise RuntimeError(f"{Path(command[0]).name} failed: {detail}")
    return result


def safe_directory(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path in {Path("/"), Path.home().resolve()}:
        raise ValueError("Refusing a broad backup directory target.")
    if path.exists() and path.is_symlink():
        raise ValueError("Backup directory may not be a symlink.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ValueError("Backup target is not a directory.")
    return path
