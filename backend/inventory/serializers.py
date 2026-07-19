from rest_framework import serializers

from .models import Category, Product, StockMovement


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "product_count")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "sku",
            "barcode",
            "name",
            "category",
            "category_name",
            "unit",
            "unit_display",
            "quantity_on_hand",
            "safety_stock",
            "reorder_quantity",
            "cost_price",
            "is_active",
            "is_low_stock",
            "created_at",
            "updated_at",
        )
        # Stock is a cache written only by record_movement(); never let it be
        # set directly through the product endpoint.
        read_only_fields = ("quantity_on_hand", "created_at", "updated_at")

    def validate_barcode(self, value):
        # Postgres allows many NULLs under a unique index but only one "".
        # An absent barcode must be NULL so a second barcode-less product saves.
        return value or None


class StockMovementSerializer(serializers.ModelSerializer):
    """Read view of a ledger row."""

    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "product",
            "product_sku",
            "product_name",
            "quantity_delta",
            "reason",
            "reason_display",
            "purchase_order",
            "note",
            "created_by",
            "created_by_username",
            "created_at",
        )
        read_only_fields = fields


class StockMovementCreateSerializer(serializers.Serializer):
    """Write path for a stock movement. Applied through record_movement()."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity_delta = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=StockMovement.Reason.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    allow_negative = serializers.BooleanField(required=False, default=False)

    def validate_quantity_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("quantity_delta must be non-zero.")
        return value
