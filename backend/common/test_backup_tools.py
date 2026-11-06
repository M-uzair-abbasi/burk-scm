import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import backup_postgres, prune_backups, restore_postgres  # noqa: E402


class BackupToolTests(SimpleTestCase):
    def test_backup_is_atomic_validated_and_never_places_password_in_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            calls = []

            def fake_run(command, *, env, capture_output, text, check):
                calls.append((command, env.copy()))
                if Path(command[0]).name == "pg_dump":
                    output = next(
                        value.split("=", 1)[1]
                        for value in command
                        if value.startswith("--file=")
                    )
                    Path(output).write_bytes(b"trusted custom archive")
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("scripts.postgres_utils.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
                patch("scripts.postgres_utils.subprocess.run", side_effect=fake_run),
            ):
                result = backup_postgres.create_backup(
                    "postgres://burk:top-secret@localhost:5433/burk_scm",
                    output_dir,
                )

            self.assertTrue(result.archive.exists())
            self.assertFalse(any(output_dir.glob("*.partial")))
            metadata = json.loads(result.metadata.read_text())
            self.assertEqual(metadata["sha256"], hashlib.sha256(result.archive.read_bytes()).hexdigest())
            self.assertEqual(metadata["database"], "burk_scm")
            rendered_commands = " ".join(" ".join(command) for command, _env in calls)
            self.assertNotIn("top-secret", rendered_commands)
            self.assertTrue(all(env["PGPASSWORD"] == "top-secret" for _command, env in calls))
            self.assertEqual([Path(command[0]).name for command, _env in calls], ["pg_dump", "pg_restore"])

    def test_restore_refuses_unsafe_target_confirmation_and_bad_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "backup.dump"
            archive.write_bytes(b"archive")
            metadata = Path(directory) / "backup.json"
            metadata.write_text(
                json.dumps(
                    {
                        "archive": archive.name,
                        "database": "burk_scm",
                        "sha256": hashlib.sha256(b"archive").hexdigest(),
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "restore target"):
                restore_postgres.restore_backup(
                    archive,
                    metadata,
                    "postgres://burk:secret@localhost:5433/burk_scm",
                    confirm_target="burk_scm",
                )
            with self.assertRaisesRegex(ValueError, "confirmation"):
                restore_postgres.restore_backup(
                    archive,
                    metadata,
                    "postgres://burk:secret@localhost:5433/burk_scm_restore_safe",
                    confirm_target="different_database",
                )

            archive.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                restore_postgres.restore_backup(
                    archive,
                    metadata,
                    "postgres://burk:secret@localhost:5433/burk_scm_restore_safe",
                    confirm_target="burk_scm_restore_safe",
                )

    def test_restore_verifies_core_tables_and_cleanup_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "backup.dump"
            archive.write_bytes(b"archive")
            metadata = Path(directory) / "backup.json"
            metadata.write_text(
                json.dumps(
                    {
                        "archive": archive.name,
                        "database": "burk_scm",
                        "sha256": hashlib.sha256(b"archive").hexdigest(),
                    }
                )
            )
            calls = []

            def fake_run(command, *, env, capture_output, text, check):
                calls.append((command, env.copy()))
                stdout = "42\n" if Path(command[0]).name == "psql" else ""
                return subprocess.CompletedProcess(command, 0, stdout, "")

            with (
                patch("scripts.postgres_utils.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
                patch("scripts.postgres_utils.subprocess.run", side_effect=fake_run),
            ):
                result = restore_postgres.restore_backup(
                    archive,
                    metadata,
                    "postgres://burk:top-secret@localhost:5433/burk_scm_restore_safe",
                    confirm_target="burk_scm_restore_safe",
                    cleanup_after_verify=True,
                )

            names = [Path(command[0]).name for command, _env in calls]
            self.assertEqual(names[0], "createdb")
            self.assertIn("pg_restore", names)
            self.assertEqual(names.count("psql"), 4)
            self.assertEqual(names[-1], "dropdb")
            self.assertEqual(result.counts["django_migrations"], 42)
            self.assertTrue(result.cleaned_up)
            self.assertNotIn("top-secret", " ".join(" ".join(command) for command, _env in calls))


class BackupRetentionTests(SimpleTestCase):
    def test_pruning_is_dry_run_by_default_and_preserves_newest_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "burk-scm_old.dump"
            newest = root / "burk-scm_new.dump"
            old.write_bytes(b"old")
            newest.write_bytes(b"new")
            old.touch()
            newest.touch()

            with patch("scripts.prune_backups._age_days", side_effect=[40, 1]):
                preview = prune_backups.prune(root, retention_days=30, apply=False)
            self.assertEqual(preview, [old])
            self.assertTrue(old.exists())

            with patch("scripts.prune_backups._age_days", side_effect=[40, 1]):
                applied = prune_backups.prune(root, retention_days=30, apply=True)
            self.assertEqual(applied, [old])
            self.assertFalse(old.exists())
            self.assertTrue(newest.exists())
