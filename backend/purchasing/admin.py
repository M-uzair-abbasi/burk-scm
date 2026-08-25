from django.contrib import admin

from common.admin import ReadOnlyAdminMixin, ReadOnlyInlineMixin

from .models import PurchaseOrder, PurchaseOrderLine


class PurchaseOrderLineInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    autocomplete_fields = ("product",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "po_number",
        "supplier",
        "status",
        "expected_date",
        "total_display",
        "created_at",
    )
    list_filter = ("status", "supplier")
    search_fields = ("po_number", "supplier__name")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at", "submitted_at", "received_at")
    inlines = [PurchaseOrderLineInline]

    @admin.display(description="Total (PKR)")
    def total_display(self, obj):
        return obj.total_amount
