from django.contrib import admin

from common.admin import ReadOnlyAdminMixin

from .models import WorkItem, WorkerHeartbeat


@admin.register(WorkItem)
class WorkItemAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "kind",
        "key",
        "status",
        "attempts",
        "correlation_id",
        "available_at",
        "locked_by",
    )
    list_filter = ("kind", "status")
    search_fields = ("key", "last_error")


@admin.register(WorkerHeartbeat)
class WorkerHeartbeatAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "last_seen_at",
        "last_claimed",
        "last_succeeded",
        "last_failed",
    )
