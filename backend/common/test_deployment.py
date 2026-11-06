import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]


class ProductionPackagingTests(SimpleTestCase):
    def _compose_config(self):
        docker = shutil.which("docker")
        self.assertIsNotNone(docker, "Docker CLI is required to validate Compose.")
        environment = {
            **os.environ,
            "POSTGRES_DB": "burk_scm",
            "POSTGRES_USER": "burk_scm",
            "POSTGRES_PASSWORD": "compose-validation-only",
            "DATABASE_URL": "postgres://burk_scm:compose-validation-only@db:5432/burk_scm",
            "SECRET_KEY": "compose-validation-secret-32-characters-long",
            "ALLOWED_HOSTS": "scm.example.invalid",
            "FRONTEND_ORIGIN": "https://scm.example.invalid",
            "PUBLIC_APP_ORIGIN": "https://scm.example.invalid",
            "BURK_SCM_ENV_FILE": ".env.production.example",
        }
        result = subprocess.run(
            [
                docker,
                "compose",
                "-f",
                "compose.prod.yml",
                "config",
                "--format",
                "json",
            ],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_compose_has_explicit_startup_gates_and_only_proxy_is_published(self):
        config = self._compose_config()
        services = config["services"]
        self.assertEqual(
            set(services),
            {"api", "db", "frontend", "migrate", "proxy", "worker"},
        )
        self.assertEqual(
            {name for name, service in services.items() if service.get("ports")},
            {"proxy"},
        )
        self.assertEqual(
            services["api"]["depends_on"]["migrate"]["condition"],
            "service_completed_successfully",
        )
        self.assertEqual(
            services["worker"]["depends_on"]["migrate"]["condition"],
            "service_completed_successfully",
        )
        self.assertIn("migrate --noinput", " ".join(services["migrate"]["command"]))
        self.assertIn("collectstatic --noinput", " ".join(services["migrate"]["command"]))
        for name in ("db", "api", "worker", "frontend", "proxy"):
            self.assertIn("healthcheck", services[name], name)
        for name in ("api", "worker", "frontend", "proxy"):
            self.assertEqual(services[name]["restart"], "unless-stopped", name)
        for name in ("db", "api", "worker", "frontend", "proxy"):
            self.assertEqual(services[name]["logging"]["driver"], "json-file", name)
            self.assertEqual(services[name]["logging"]["options"]["max-size"], "10m", name)
            self.assertEqual(services[name]["logging"]["options"]["max-file"], "5", name)

    def test_private_media_and_database_are_not_exposed(self):
        config = self._compose_config()
        services = config["services"]
        self.assertNotIn("ports", services["db"])
        self.assertNotIn("ports", services["api"])
        self.assertNotIn("ports", services["frontend"])
        proxy_mount_sources = {
            mount.get("source")
            for mount in services["proxy"].get("volumes", [])
            if isinstance(mount, dict)
        }
        self.assertNotIn("private_media", proxy_mount_sources)

        nginx = (REPO_ROOT / "deploy/nginx.conf").read_text()
        self.assertIn("location ^~ /media/", nginx)
        self.assertIn("return 404", nginx)
        self.assertIn("X-Content-Type-Options", nginx)
        self.assertIn("Content-Security-Policy", nginx)

    def test_images_are_locked_non_root_and_use_production_servers(self):
        backend_dockerfile = (REPO_ROOT / "backend/Dockerfile").read_text()
        frontend_dockerfile = (REPO_ROOT / "frontend/Dockerfile").read_text()
        next_config = (REPO_ROOT / "frontend/next.config.ts").read_text()
        pyproject = tomllib.loads((REPO_ROOT / "backend/pyproject.toml").read_text())

        self.assertIn("uv sync --frozen", backend_dockerfile)
        self.assertIn("USER app", backend_dockerfile)
        self.assertIn("gunicorn", backend_dockerfile)
        self.assertNotIn("runserver", backend_dockerfile)
        self.assertIn("npm ci", frontend_dockerfile)
        self.assertIn("USER nextjs", frontend_dockerfile)
        self.assertIn(".next/standalone", frontend_dockerfile)
        self.assertIn('output: "standalone"', next_config)
        self.assertTrue(
            any(
                dependency.startswith("gunicorn")
                for dependency in pyproject["project"]["dependencies"]
            )
        )
