from pathlib import Path
import re

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]


class ContinuousIntegrationContractTests(SimpleTestCase):
    def test_workflow_is_postgresql_locked_and_runs_every_release_gate(self):
        workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()

        for required in (
            "postgres:16",
            "pg_isready",
            "uv sync --frozen",
            "manage.py test",
            "ConcurrentMovementTests",
            "makemigrations --check --dry-run",
            "check --deploy --fail-level WARNING",
            "check_release_policy",
            "check_order_integrity --check",
            "check_operational_metrics --check",
            "docker compose",
            "npm ci",
            "npm run typecheck",
            "npm run lint",
            "npm run build",
            ".next/standalone/server.js",
        ):
            self.assertIn(required, workflow)
        self.assertIn("django.db.backends.postgresql", workflow)
        self.assertNotIn("sqlite", workflow.lower())

    def test_actions_are_sha_pinned_and_caches_exclude_secrets_and_media(self):
        workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text()
        action_refs = re.findall(r"uses:\s*[^\s@]+@([^\s#]+)", workflow)
        self.assertGreaterEqual(len(action_refs), 3)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))

        cache_lines = "\n".join(
            line for line in workflow.splitlines() if "cache" in line.lower()
        ).lower()
        self.assertNotIn("secret", cache_lines)
        self.assertNotIn("media", cache_lines)
