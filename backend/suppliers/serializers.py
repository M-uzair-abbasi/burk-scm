from rest_framework import serializers

from .models import Supplier, SupplierPriceTier, SupplierProduct


class SupplierPriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPriceTier
        fields = ("id", "supplier_product", "min_quantity", "unit_price")


class SupplierProductSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    effective_lead_time_days = serializers.IntegerField(read_only=True)
    price_tiers = SupplierPriceTierSerializer(many=True, read_only=True)

    class Meta:
        model = SupplierProduct
        fields = (
            "id",
            "supplier",
            "supplier_name",
            "product",
            "product_sku",
            "product_name",
            "supplier_sku",
            "lead_time_days",
            "effective_lead_time_days",
            "is_preferred",
            "is_active",
            "price_tiers",
        )


class SupplierSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(
        source="supplier_products.count", read_only=True
    )

    class Meta:
        model = Supplier
        fields = (
            "id",
            "code",
            "name",
            "contact_person",
            "email",
            "phone",
            "address",
            "city",
            "default_lead_time_days",
            "payment_terms",
            "is_active",
            "notes",
            "product_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
