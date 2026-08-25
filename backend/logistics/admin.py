from django.contrib import admin

from common.admin import ReadOnlyAdminMixin, ReadOnlyInlineMixin

from .models import CourierWebhookEvent, Shipment, ShipmentEvent


class ShipmentEventInline(ReadOnlyInlineMixin, admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    can_delete = False
    fields = ("occurred_at", "status", "source")
    readonly_fields = fields


@admin.register(Shipment)
class ShipmentAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("tracking_number", "order", "courier", "status", "booked_at", "delivered_at")
    list_filter = ("courier", "status")
    search_fields = ("tracking_number", "order__reference")
    inlines = [ShipmentEventInline]
    readonly_fields = ("order", "courier", "tracking_number", "booked_at")


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("occurred_at", "shipment", "status", "source")
    list_filter = ("status", "source")
    readonly_fields = [f.name for f in ShipmentEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CourierWebhookEvent)
class CourierWebhookEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "received_at",
        "courier",
        "provider_event_id",
        "shipment",
        "outcome",
        "mapped_status",
    )
    list_filter = ("courier", "outcome", "mapped_status")
    search_fields = ("provider_event_id", "shipment__tracking_number")
    readonly_fields = [f.name for f in CourierWebhookEvent._meta.fields]
