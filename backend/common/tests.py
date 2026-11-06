from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase

from fulfillment.models import PackScan, PackingSession
from inventory.models import StockMovement
from logistics.models import Shipment, ShipmentEvent
from notifications.models import Notification
from orders.models import SalesOrder, SyncRun
from purchasing.models import PurchaseOrder
from surveillance.models import PackagingRecording

User = get_user_model()


class AdminWorkflowSafetyTests(TestCase):
    workflow_models = (
        StockMovement,
        PurchaseOrder,
        SalesOrder,
        SyncRun,
        PackingSession,
        PackScan,
        PackagingRecording,
        Notification,
        Shipment,
        ShipmentEvent,
    )

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin-safety",
            email="admin@example.invalid",
            password="x",
        )
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.superuser

    def test_workflow_and_ledger_admins_are_fully_read_only(self):
        for model in self.workflow_models:
            with self.subTest(model=model._meta.label):
                model_admin = admin.site._registry[model]
                self.assertFalse(model_admin.has_add_permission(self.request))
                self.assertFalse(model_admin.has_change_permission(self.request))
                self.assertFalse(model_admin.has_delete_permission(self.request))

    def test_workflow_inlines_cannot_add_change_or_delete(self):
        for parent_model in (PurchaseOrder, SalesOrder, PackingSession, Shipment):
            parent_admin = admin.site._registry[parent_model]
            for inline_class in parent_admin.inlines:
                with self.subTest(
                    parent=parent_model._meta.label,
                    inline=inline_class.__name__,
                ):
                    inline = inline_class(parent_model, admin.site)
                    self.assertFalse(
                        inline.has_add_permission(self.request, obj=None)
                    )
                    self.assertFalse(
                        inline.has_change_permission(self.request, obj=None)
                    )
                    self.assertFalse(
                        inline.has_delete_permission(self.request, obj=None)
                    )


class DemoUserSafetyTests(TestCase):
    def test_seeded_accounts_are_neither_staff_nor_superusers(self):
        User.objects.create_superuser(
            username="manager",
            email="manager@example.invalid",
            password="legacy-password",
        )

        call_command("seed_demo", stdout=StringIO())

        manager = User.objects.get(username="manager")
        operator = User.objects.get(username="operator")
        self.assertEqual(manager.role, User.Role.MANAGER)
        self.assertFalse(manager.is_staff)
        self.assertFalse(manager.is_superuser)
        self.assertFalse(operator.is_staff)
        self.assertFalse(operator.is_superuser)


class ProductionSettingsProfileTests(SimpleTestCase):
    def _environment(self):
        return {
            **os.environ,
            "DEBUG": "False",
            "PRODUCTION_MODE": "True",
            "SECRET_KEY": "prod-test-9f0e92d86b7340e88df7bb9916ca1dfbe7554886b2ac4dc",
            "ALLOWED_HOSTS": "scm.example.com",
            "FRONTEND_ORIGIN": "https://scm.example.com",
            "DEMO_MODE_ENABLED": "False",
            "DEMO_ACTIONS_ENABLED": "False",
            "ALLOW_DEMO_RESET": "False",
        }

    def test_production_environment_loads_secure_nondemo_defaults(self):
        script = """
import json
import django
django.setup()
from django.conf import settings
print(json.dumps({
    "production": settings.PRODUCTION_MODE,
    "debug": settings.DEBUG,
    "ssl_redirect": settings.SECURE_SSL_REDIRECT,
    "session_secure": settings.SESSION_COOKIE_SECURE,
    "csrf_secure": settings.CSRF_COOKIE_SECURE,
    "hsts_seconds": settings.SECURE_HSTS_SECONDS,
    "hsts_subdomains": settings.SECURE_HSTS_INCLUDE_SUBDOMAINS,
    "hsts_preload": settings.SECURE_HSTS_PRELOAD,
    "proxy_header": settings.SECURE_PROXY_SSL_HEADER,
    "frontend_origin": settings.FRONTEND_ORIGIN,
    "demo_mode": settings.DEMO_MODE_ENABLED,
    "demo_actions": settings.DEMO_ACTIONS_ENABLED,
    "demo_reset": settings.ALLOW_DEMO_RESET,
}))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env={**self._environment(), "DJANGO_SETTINGS_MODULE": "config.settings"},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual(
            values,
            {
                "production": True,
                "debug": False,
                "ssl_redirect": True,
                "session_secure": True,
                "csrf_secure": True,
                "hsts_seconds": 31536000,
                "hsts_subdomains": True,
                "hsts_preload": True,
                "proxy_header": ["HTTP_X_FORWARDED_PROTO", "https"],
                "frontend_origin": "https://scm.example.com",
                "demo_mode": False,
                "demo_actions": False,
                "demo_reset": False,
            },
        )

    def test_production_environment_passes_django_deploy_checks(self):
        result = subprocess.run(
            [
                sys.executable,
                "manage.py",
                "check",
                "--deploy",
                "--fail-level",
                "WARNING",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=self._environment(),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
