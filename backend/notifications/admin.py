from django.contrib import admin

from common.admin import ReadOnlyAdminMixin

from .models import Notification, NotificationDeliveryEvent


@admin.register(Notification)
class NotificationAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
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


@admin.register(NotificationDeliveryEvent)
class NotificationDeliveryEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "received_at",
        "channel",
        "provider_event_id",
        "provider_status",
        "outcome",
        "notification",
    )
    list_filter = ("channel", "outcome", "provider_status")
    search_fields = ("provider_event_id", "provider_message_id")
    readonly_fields = [f.name for f in NotificationDeliveryEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
