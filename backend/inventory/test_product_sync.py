"""Tests for the WooCommerce product-catalog sync, against mocked HTTP
responses shaped like the real dev.burk.pk staging product catalog."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings

from .models import Product, StockMovement
from .services import sync_products_from_woocommerce

LIVE_SETTINGS = dict(
    BURK_ORDER_API_BASE_URL="https://dev.burk.pk",
    BURK_ORDER_API_CONSUMER_KEY="ck_test",
    BURK_ORDER_API_CONSUMER_SECRET="cs_test",
)


def _woo_product(**overrides) -> dict:
    base = {
        "id": 20399,
        "sku": "7000000000057",
        "name": "Texas Instruments Logic Converter",
        "manage_stock": True,
        "stock_quantity": 9,
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
class ProductSyncTests(TestCase):
    @patch("common.woocommerce.requests.get")
    def test_new_sku_is_created_with_opening_balance_movement(self, mock_get):
        mock_get.side_effect = [_FakeResponse([_woo_product()]), _FakeResponse([])]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["created"], 1)
        product = Product.objects.get(sku="7000000000057")
        self.assertEqual(product.quantity_on_hand, 9)
        movement = product.movements.get()
        self.assertEqual(movement.reason, StockMovement.Reason.INITIAL)
        self.assertEqual(movement.quantity_delta, 9)

    @patch("common.woocommerce.requests.get")
    def test_product_with_no_sku_is_skipped(self, mock_get):
        custom_print = _woo_product(id=46785, sku="", name="3D Print Order")
        mock_get.side_effect = [_FakeResponse([custom_print]), _FakeResponse([])]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["skipped_no_sku"], 1)
        self.assertEqual(result["created"], 0)
        self.assertFalse(Product.objects.exists())

    @patch("common.woocommerce.requests.get")
    def test_known_sku_with_no_drift_is_unchanged(self, mock_get):
        Product.objects.create(sku="7000000000057", name="old name", quantity_on_hand=9)
        mock_get.side_effect = [_FakeResponse([_woo_product()]), _FakeResponse([])]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(result["updated"], 0)
        product = Product.objects.get(sku="7000000000057")
        self.assertEqual(product.name, "Texas Instruments Logic Converter")
        self.assertFalse(product.movements.exists())

    @patch("common.woocommerce.requests.get")
    def test_known_sku_with_drift_gets_an_adjustment_movement(self, mock_get):
        Product.objects.create(sku="7000000000057", name="x", quantity_on_hand=3)
        mock_get.side_effect = [
            _FakeResponse([_woo_product(stock_quantity=9)]),
            _FakeResponse([]),
        ]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["updated"], 1)
        product = Product.objects.get(sku="7000000000057")
        self.assertEqual(product.quantity_on_hand, 9)
        movement = product.movements.get()
        self.assertEqual(movement.reason, StockMovement.Reason.ADJUSTMENT)
        self.assertEqual(movement.quantity_delta, 6)

    @patch("common.woocommerce.requests.get")
    def test_unmanaged_stock_product_treated_as_zero(self, mock_get):
        unmanaged = _woo_product(manage_stock=False, stock_quantity=None)
        mock_get.side_effect = [_FakeResponse([unmanaged]), _FakeResponse([])]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["created"], 1)
        product = Product.objects.get(sku="7000000000057")
        self.assertEqual(product.quantity_on_hand, 0)
        self.assertFalse(product.movements.exists())

    @patch("common.woocommerce.requests.get")
    def test_negative_woocommerce_stock_is_clamped_to_zero(self, mock_get):
        backordered = _woo_product(stock_quantity=-1)
        mock_get.side_effect = [_FakeResponse([backordered]), _FakeResponse([])]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["failed"], 0)
        product = Product.objects.get(sku="7000000000057")
        self.assertEqual(product.quantity_on_hand, 0)
        self.assertFalse(product.movements.exists())


def _woo_variable_parent(**overrides) -> dict:
    base = {
        "id": 22751,
        "sku": "",
        "name": "Cap Nuts",
        "type": "variable",
        "manage_stock": True,
        "stock_quantity": None,
    }
    base.update(overrides)
    return base


def _woo_variation(**overrides) -> dict:
    base = {
        "id": 22758,
        "sku": "1000000000085",
        "manage_stock": True,
        "stock_quantity": 20,
        "attributes": [{"id": 0, "name": "Size", "slug": "size", "option": "M10"}],
    }
    base.update(overrides)
    return base


@override_settings(**LIVE_SETTINGS)
class VariableProductSyncTests(TestCase):
    @patch("common.woocommerce.requests.get")
    def test_variable_parent_itself_is_never_created_as_a_product(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse([_woo_variable_parent()]),  # products page 1 (1 item, stops)
            _FakeResponse([_woo_variation()]),  # variations page 1 (1 item, stops)
        ]

        sync_products_from_woocommerce()

        self.assertFalse(Product.objects.filter(sku="").exists())
        self.assertEqual(Product.objects.count(), 1)

    @patch("common.woocommerce.requests.get")
    def test_variations_are_synced_with_real_skus_and_combined_name(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse([_woo_variable_parent()]),
            _FakeResponse([_woo_variation()]),
        ]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["created"], 1)
        product = Product.objects.get(sku="1000000000085")
        self.assertEqual(product.name, "Cap Nuts - M10")
        self.assertEqual(product.quantity_on_hand, 20)

    @patch("common.woocommerce.requests.get")
    def test_variation_with_no_sku_is_skipped(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse([_woo_variable_parent()]),
            _FakeResponse([_woo_variation(sku="")]),
        ]

        result = sync_products_from_woocommerce()

        self.assertEqual(result["skipped_no_sku"], 1)
        self.assertFalse(Product.objects.exists())
