from django.contrib import admin

from .models import SalesOrder, SalesOrderLine, SyncRun


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 0
    can_delete = False
    fields = ("sku", "product", "product_name", "quantity", "unit_price", "line_total")
    readonly_fields = fields


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "channel",
        "external_id",
        "status",
        "customer_name",
        "item_count",
        "total",
        "placed_at",
    )
    list_filter = ("channel", "status")
    search_fields = ("reference", "external_id", "customer_name", "customer_phone")
    date_hierarchy = "placed_at"
    inlines = [SalesOrderLineInline]
    readonly_fields = (
        "reference",
        "channel",
        "external_id",
        "ingested_at",
        "last_synced_at",
        "updated_at",
        "raw_payload",
    )


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = (
        "channel",
        "started_at",
        "finished_at",
        "fetched",
        "created",
        "updated",
        "duplicates_skipped",
        "failed",
        "ok",
    )
    list_filter = ("channel", "ok")
    readonly_fields = [f.name for f in SyncRun._meta.fields]

    # Append-only: the admin views history, it does not author it.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
