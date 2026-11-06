"""Contract tests for environment-selected external integration adapters."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from logistics.couriers import get_carrier
from notifications.channels import get_channel
from notifications.reviews import get_review_link_provider
from orders.connectors import get_connector
from surveillance.camera import get_camera


DEMO_BACKENDS = {
    "DEMO_MODE_ENABLED": True,
    "ORDER_CONNECTOR_BACKENDS": {"burk": "fixture", "daraz": "fixture"},
    "PACKAGING_CAMERA_BACKEND": "simulated",
    "COURIER_BACKEND": "simulated",
    "WHATSAPP_BACKEND": "simulated",
    "REVIEW_LINK_BACKEND": "simulated",
    "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
}

LIVE_BACKENDS = {
    "DEMO_MODE_ENABLED": False,
    "ORDER_CONNECTOR_BACKENDS": {"burk": "live", "daraz": "live"},
    "PACKAGING_CAMERA_BACKEND": "browser",
    "COURIER_BACKEND": "live_leopard",
    "WHATSAPP_BACKEND": "live",
    "REVIEW_LINK_BACKEND": "live_burk",
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example.invalid",
}


class AdapterSelectionTests(SimpleTestCase):
    @override_settings(**DEMO_BACKENDS)
    def test_demo_configuration_selects_fixture_adapters(self):
        selected = {
            get_connector("burk").__class__.__name__,
            get_connector("daraz").__class__.__name__,
            get_camera().__class__.__name__,
            get_carrier().__class__.__name__,
            get_channel("whatsapp").__class__.__name__,
            get_review_link_provider().__class__.__name__,
        }

        self.assertEqual(
            selected,
            {
                "BurkConnector",
                "DarazConnector",
                "SimulatedOverheadCameraAdapter",
                "SimulatedCourierAdapter",
                "SimulatedWhatsAppChannel",
                "SimulatedReviewLinkProvider",
            },
        )

    @override_settings(**LIVE_BACKENDS)
    def test_live_configuration_selects_live_adapter_slots_without_source_edits(self):
        selected = {
            get_connector("burk").__class__.__name__,
            get_connector("daraz").__class__.__name__,
            get_camera().__class__.__name__,
            get_carrier().__class__.__name__,
            get_channel("whatsapp").__class__.__name__,
            get_review_link_provider().__class__.__name__,
        }

        self.assertEqual(
            selected,
            {
                "LiveBurkConnector",
                "LiveDarazConnector",
                "BrowserCameraAdapter",
                "LiveLeopardAdapter",
                "LiveWhatsAppChannel",
                "LiveBurkReviewLinkProvider",
            },
        )

    @override_settings(DEMO_MODE_ENABLED=False, **{
        key: value for key, value in DEMO_BACKENDS.items()
        if key != "DEMO_MODE_ENABLED"
    })
    def test_fixture_adapters_are_refused_outside_demo_mode(self):
        factories = (
            lambda: get_connector("burk"),
            lambda: get_connector("daraz"),
            get_camera,
            get_carrier,
            lambda: get_channel("email"),
            lambda: get_channel("whatsapp"),
            get_review_link_provider,
        )

        for factory in factories:
            with self.subTest(factory=factory):
                with self.assertRaises(ImproperlyConfigured):
                    factory()

    @override_settings(PRODUCTION_MODE=True, **DEMO_BACKENDS)
    def test_production_mode_refuses_fixtures_even_if_demo_was_misconfigured(self):
        with self.assertRaises(ImproperlyConfigured):
            get_connector("daraz")

    @override_settings(
        **LIVE_BACKENDS,
        DARAZ_APP_KEY="",
        DARAZ_APP_SECRET="",
        DARAZ_ACCESS_TOKEN="",
        DARAZ_API_BASE_URL="",
        BURK_ORDER_API_BASE_URL="",
        BURK_ORDER_API_CONSUMER_KEY="",
        BURK_ORDER_API_CONSUMER_SECRET="",
    )
    def test_live_connector_health_names_missing_settings_without_secret_values(self):
        daraz = get_connector("daraz").health()
        burk = get_connector("burk").health()

        self.assertEqual(
            set(daraz["missing_settings"]),
            {
                "DARAZ_APP_KEY",
                "DARAZ_APP_SECRET",
                "DARAZ_ACCESS_TOKEN",
                "DARAZ_API_BASE_URL",
            },
        )
        self.assertEqual(
            set(burk["missing_settings"]),
            {
                "BURK_ORDER_API_BASE_URL",
                "BURK_ORDER_API_CONSUMER_KEY",
                "BURK_ORDER_API_CONSUMER_SECRET",
            },
        )
