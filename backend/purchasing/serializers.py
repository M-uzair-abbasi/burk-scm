from rest_framework import serializers

from inventory.models import Product
from suppliers.models import Supplier

from .models import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    quantity_outstanding = serializers.IntegerField(read_only=True)
    line_total = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = PurchaseOrderLine
        fields = (
            "id",
            "product",
            "product_sku",
            "product_name",
            "quantity_ordered",
            "unit_price",
            "quantity_received",
            "quantity_outstanding",
            "line_total",
        )
        read_only_fields = ("quantity_received",)


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "po_number",
            "supplier",
            "supplier_name",
            "status",
            "status_display",
            "expected_date",
            "notes",
            "created_by",
            "created_by_username",
            "lines",
            "total_amount",
            "is_open",
            "created_at",
            "updated_at",
            "submitted_at",
            "received_at",
        )
        read_only_fields = fields


class PurchaseOrderLineWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity_ordered = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class PurchaseOrderWriteSerializer(serializers.Serializer):
    """Manual draft-PO creation with explicit lines."""

    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    expected_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = PurchaseOrderLineWriteSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("A purchase order needs at least one line.")
        product_ids = [line["product"].id for line in value]
        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError("A product may appear on only one line.")
        return value


class ReorderSerializer(serializers.Serializer):
    """Input for the reorder-from-product action."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(required=False, min_value=1)
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False
    )


class ReceiptLineSerializer(serializers.Serializer):
    line = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class ReceiveSerializer(serializers.Serializer):
    """Optional partial-receipt payload; omit to receive everything outstanding."""

    receipts = ReceiptLineSerializer(many=True, required=False)
