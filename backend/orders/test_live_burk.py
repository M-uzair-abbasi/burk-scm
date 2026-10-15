"""Tests for the live WooCommerce connector, against mocked HTTP responses
shaped like the real dev.burk.pk staging API (verified by hand against a real
order and the real product catalog before writing this connector)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from .connectors.live_burk import LiveBurkConnector

LIVE_SETTINGS = dict(
    BURK_ORDER_API_BASE_URL="https://dev.burk.pk",
    BURK_ORDER_API_CONSUMER_KEY="ck_test",
    BURK_ORDER_API_CONSUMER_SECRET="cs_test",
)


def _woo_order(**overrides) -> dict:
    base = {
        "id": 46786,
        "status": "processing",
        "currency": "PKR",
        "total": "3760.00",
        "shipping_total": "150.00",
        "payment_method": "cod",
        "customer_note": "Leave with the guard if not home.",
        "date_created": "2026-10-05T13:11:26",
        "date_created_gmt": "2026-10-05T08:11:26",
        "billing": {
            "first_name": "Usman",
            "last_name": "Zafar",
            "email": "usman@example.invalid",
            "phone": "03000884503",
        },
        "shipping": {
            "address_1": "Street 49",
            "address_2": "Plot 1198",
            "city": "Islamabad",
            "state": "IS",
            "postcode": "46000",
            "country": "PK",
        },
        "line_items": [
            {
                "sku": "7000000000057",
                "name": "Logic Converter",
                "quantity": 2,
                "total": "3760.00",
            }
        ],
    }
    base.update(overrides)
    return base


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@override_settings(**LIVE_SETTINGS)
class FetchPaginationTests(TestCase):
    @patch("common.woocommerce.requests.get")
    def test_fetch_follows_pagination_until_a_short_page(self, mock_get):
        full_page = [_woo_order(id=i) for i in range(50)]
        short_page = [_woo_order(id=50)]
        mock_get.side_effect = [
            _FakeResponse(full_page),
            _FakeResponse(short_page),
        ]

        orders = LiveBurkConnector().fetch()

        self.assertEqual(len(orders), 51)
        self.assertEqual(mock_get.call_count, 2)


@override_settings(**LIVE_SETTINGS)
class SkuScopingTests(TestCase):
    @patch("common.woocommerce.requests.get")
    def test_order_with_every_line_skued_is_included(self, mock_get):
        mock_get.side_effect = [_FakeResponse([_woo_order()]), _FakeResponse([])]

        orders = LiveBurkConnector().fetch()

        self.assertEqual(len(orders), 1)

    @patch("common.woocommerce.requests.get")
    def test_order_with_an_unskued_line_is_excluded(self, mock_get):
        custom_print = _woo_order(
            id=99,
            line_items=[
                {"sku": "", "name": "3D Print Order", "quantity": 1, "total": "500"}
            ],
        )
        mock_get.side_effect = [_FakeResponse([custom_print]), _FakeResponse([])]

        orders = LiveBurkConnector().fetch()

        self.assertEqual(orders, [])

    @patch("common.woocommerce.requests.get")
    def test_order_with_one_skued_and_one_unskued_line_is_excluded(self, mock_get):
        mixed = _woo_order(
            id=100,
            line_items=[
                _woo_order()["line_items"][0],
                {"sku": "", "name": "3D Print Order", "quantity": 1, "total": "500"},
            ],
        )
        mock_get.side_effect = [_FakeResponse([mixed]), _FakeResponse([])]

        orders = LiveBurkConnector().fetch()

        self.assertEqual(orders, [])

    @patch("common.woocommerce.requests.get")
    def test_order_with_no_line_items_is_excluded(self, mock_get):
        empty = _woo_order(id=101, line_items=[])
        mock_get.side_effect = [_FakeResponse([empty]), _FakeResponse([])]

        orders = LiveBurkConnector().fetch()

        self.assertEqual(orders, [])


class NormalizeTests(TestCase):
    def test_maps_a_real_shaped_cod_order(self):
        norm = LiveBurkConnector().normalize(_woo_order())

        self.assertEqual(norm.channel, "burk")
        self.assertEqual(norm.external_id, "46786")
        self.assertEqual(norm.status, "confirmed")  # WooCommerce "processing"
        self.assertEqual(norm.customer_name, "Usman Zafar")
        self.assertEqual(norm.customer_phone, "03000884503")
        self.assertEqual(norm.customer_email, "usman@example.invalid")
        self.assertEqual(norm.shipping_city, "Islamabad")
        self.assertEqual(norm.shipping_country, "PK")
        self.assertEqual(norm.payment_mode, "cod")
        self.assertEqual(norm.cod_amount, Decimal("3760.00"))
        self.assertEqual(norm.total, Decimal("3760.00"))
        self.assertEqual(norm.shipping_fee, Decimal("150.00"))
        self.assertEqual(norm.subtotal, Decimal("3610.00"))
        self.assertEqual(len(norm.lines), 1)
        self.assertEqual(norm.lines[0].sku, "7000000000057")
        self.assertEqual(norm.lines[0].quantity, 2)
        self.assertEqual(norm.lines[0].unit_price, Decimal("1880.00"))
        # Must come from date_created_gmt (UTC), not the site-local sibling.
        self.assertEqual(norm.placed_at.hour, 8)
        self.assertEqual(norm.placed_at.utcoffset().total_seconds(), 0)

    def test_prepaid_order_has_zero_cod_amount(self):
        norm = LiveBurkConnector().normalize(
            _woo_order(payment_method="bacs", status="completed")
        )

        self.assertEqual(norm.payment_mode, "prepaid")
        self.assertEqual(norm.cod_amount, Decimal("0.00"))
        self.assertEqual(norm.status, "delivered")  # WooCommerce "completed"

    def test_unknown_status_falls_back_to_pending(self):
        norm = LiveBurkConnector().normalize(_woo_order(status="checkout-draft"))

        self.assertEqual(norm.status, "pending")


class HealthTests(TestCase):
    @override_settings(
        BURK_ORDER_API_BASE_URL="",
        BURK_ORDER_API_CONSUMER_KEY="",
        BURK_ORDER_API_CONSUMER_SECRET="",
    )
    def test_health_names_missing_settings(self):
        health = LiveBurkConnector().health()

        self.assertFalse(health["ok"])
        self.assertEqual(
            set(health["missing_settings"]),
            {
                "BURK_ORDER_API_BASE_URL",
                "BURK_ORDER_API_CONSUMER_KEY",
                "BURK_ORDER_API_CONSUMER_SECRET",
            },
        )

    @override_settings(**LIVE_SETTINGS)
    @patch("common.woocommerce.requests.get")
    def test_health_pings_instead_of_fetching_everything(self, mock_get):
        mock_get.return_value = _FakeResponse([_woo_order()])
        mock_get.return_value.headers = {"X-WP-Total": "92"}

        health = LiveBurkConnector().health()

        self.assertTrue(health["ok"])
        self.assertEqual(health["records_available"], 92)
        # One ping, not fetch_all's full pagination.
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_get.call_args.kwargs["params"]["per_page"], 1)

    @override_settings(**LIVE_SETTINGS)
    @patch("common.woocommerce.requests.get")
    def test_health_reports_unreachable_api(self, mock_get):
        mock_get.side_effect = ConnectionError("staging is down")

        health = LiveBurkConnector().health()

        self.assertFalse(health["ok"])
        self.assertEqual(health["error_class"], "ConnectionError")
