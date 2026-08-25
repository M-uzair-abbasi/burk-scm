from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from common.release import release_configuration_violations


LIVE_SETTINGS = {
    "DEBUG": False,
    "PRODUCTION_MODE": True,
    "SECRET_KEY": "release-policy-key-9f0e92d86b7340e88df7bb9916ca1dfbe7554886b2ac4dc",
    "ALLOWED_HOSTS": ["scm.burk.pk"],
    "FRONTEND_ORIGIN": "https://scm.burk.pk",
    "PUBLIC_APP_ORIGIN": "https://scm.burk.pk",
    "DEMO_MODE_ENABLED": False,
    "DEMO_ACTIONS_ENABLED": False,
    "ALLOW_DEMO_RESET": False,
    "REQUIRE_LIVE_INTEGRATIONS": True,
    "ORDER_CONNECTOR_BACKENDS": {"burk": "live", "daraz": "live"},
    "PACKAGING_CAMERA_BACKEND": "live",
    "COURIER_BACKEND": "live_leopard",
    "WHATSAPP_BACKEND": "live",
    "REVIEW_LINK_BACKEND": "live_burk",
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.staging.vendor.test",
    "DATABASES": {"default": {"ENGINE": "django.db.backends.postgresql"}},
    "DARAZ_APP_KEY": "configured-daraz-key",
    "DARAZ_APP_SECRET": "configured-daraz-secret",
    "DARAZ_ACCESS_TOKEN": "configured-daraz-token",
    "DARAZ_API_BASE_URL": "https://daraz.staging.vendor.test",
    "BURK_ORDER_API_BASE_URL": "https://orders.staging.burk.pk",
    "BURK_ORDER_API_TOKEN": "configured-burk-token",
    "PACKAGING_CAMERA_SOURCE": "rtsp://camera.internal/stream",
    "LEOPARD_API_KEY": "configured-leopard-key",
    "LEOPARD_API_PASSWORD": "configured-leopard-password",
    "COURIER_WEBHOOK_SECRETS": {"leopard": "configured-courier-webhook"},
    "WHATSAPP_ACCESS_TOKEN": "configured-whatsapp-token",
    "WHATSAPP_PHONE_NUMBER_ID": "123456789",
    "NOTIFICATION_WEBHOOK_SECRETS": {"whatsapp": "configured-notification-webhook"},
    "BURK_REVIEW_API_BASE_URL": "https://reviews.staging.burk.pk",
    "BURK_REVIEW_API_TOKEN": "configured-review-token",
}


class ReleasePolicyTests(SimpleTestCase):
    @override_settings(
        DEBUG=True,
        PRODUCTION_MODE=True,
        DEMO_MODE_ENABLED=True,
        DEMO_ACTIONS_ENABLED=True,
        ORDER_CONNECTOR_BACKENDS={"burk": "fixture", "daraz": "fixture"},
        PACKAGING_CAMERA_BACKEND="simulated",
        COURIER_BACKEND="simulated",
        WHATSAPP_BACKEND="simulated",
        REVIEW_LINK_BACKEND="simulated",
    )
    def test_policy_rejects_debug_demo_and_every_simulated_slot(self):
        violations = release_configuration_violations()
        rendered = " ".join(violations)

        for expected in (
            "DEBUG",
            "DEMO_MODE_ENABLED",
            "DEMO_ACTIONS_ENABLED",
            "orders.burk",
            "orders.daraz",
            "camera",
            "courier",
            "WhatsApp",
            "review",
        ):
            self.assertIn(expected, rendered)

    @override_settings(**LIVE_SETTINGS)
    def test_complete_live_configuration_passes_without_exposing_values(self):
        self.assertEqual(release_configuration_violations(), [])
        output = StringIO()
        call_command("check_release_policy", stdout=output)
        rendered = output.getvalue()
        self.assertIn("Release configuration policy OK", rendered)
        self.assertNotIn("configured-daraz-secret", rendered)
        self.assertNotIn("configured-whatsapp-token", rendered)
