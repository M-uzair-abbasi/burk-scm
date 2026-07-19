from django.contrib import admin

from .models import Supplier, SupplierPriceTier, SupplierProduct


class SupplierPriceTierInline(admin.TabularInline):
    model = SupplierPriceTier
    extra = 1


class SupplierProductInline(admin.TabularInline):
    model = SupplierProduct
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "city",
        "contact_person",
        "default_lead_time_days",
        "is_active",
    )
    list_filter = ("is_active", "city")
    search_fields = ("code", "name", "contact_person", "email")
    inlines = [SupplierProductInline]


@admin.register(SupplierProduct)
class SupplierProductAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "supplier",
        "supplier_sku",
        "lead_time_display",
        "is_preferred",
        "is_active",
    )
    list_filter = ("is_preferred", "is_active", "supplier")
    search_fields = ("product__sku", "product__name", "supplier__name")
    autocomplete_fields = ("product", "supplier")
    inlines = [SupplierPriceTierInline]

    @admin.display(description="Lead time (days)")
    def lead_time_display(self, obj) -> int:
        return obj.effective_lead_time_days
