from django.contrib import admin

from common.admin import ReadOnlyAdminMixin, ReadOnlyInlineMixin

from .models import PackingSession, PackScan


class PackScanInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = PackScan
    extra = 0
    can_delete = False
    fields = ("scanned_at", "barcode", "result", "product", "line", "manual", "operator")
    readonly_fields = fields


@admin.register(PackingSession)
class PackingSessionAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("id", "order", "status", "operator", "started_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("order__reference", "order__external_id")
    inlines = [PackScanInline]
    readonly_fields = ("order", "operator", "started_at", "completed_at")


@admin.register(PackScan)
class PackScanAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("scanned_at", "session", "barcode", "result", "product", "manual", "operator")
    list_filter = ("result", "manual")
    search_fields = ("barcode",)
    readonly_fields = [f.name for f in PackScan._meta.fields]

    # Append-only: the admin views scan history, it does not author it.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
