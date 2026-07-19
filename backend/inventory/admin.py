from django.contrib import admin

from .models import Category, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "quantity_on_hand",
        "safety_stock",
        "is_low_stock",
        "is_active",
    )
    list_filter = ("is_active", "category", "unit")
    search_fields = ("sku", "name", "barcode")
    # quantity_on_hand is a cache of the ledger; editing it here would create
    # drift that no movement explains.
    readonly_fields = ("quantity_on_hand", "created_at", "updated_at")

    @admin.display(boolean=True, description="Low stock")
    def is_low_stock(self, obj) -> bool:
        return obj.is_low_stock


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "product",
        "quantity_delta",
        "reason",
        "purchase_order",
        "created_by",
    )
    list_filter = ("reason", "created_at")
    search_fields = ("product__sku", "product__name", "note")
    date_hierarchy = "created_at"

    # The ledger is append-only: it is read here, never edited.
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        # Stock only moves through record_movement(), which keeps the cache
        # in step. A raw admin insert would silently desync it.
        return False
