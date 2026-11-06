from django.contrib import admin

from common.admin import ReadOnlyAdminMixin

from .models import PackagingRecording


@admin.register(PackagingRecording)
class PackagingRecordingAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "session",
        "status",
        "duration_seconds",
        "capture_started_at",
        "sealed_at",
        "compressed_at",
    )
    list_filter = ("status",)
    search_fields = ("session__order__reference",)
    readonly_fields = [f.name for f in PackagingRecording._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
