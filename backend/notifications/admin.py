from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "order",
        "kind",
        "channel",
        "recipient",
        "status",
        "sent_at",
    )
    list_filter = ("kind", "channel", "status")
    search_fields = ("order__reference", "recipient")
    readonly_fields = [f.name for f in Notification._meta.fields]

    # System-authored: dispatch() creates these, the admin is for inspection.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
