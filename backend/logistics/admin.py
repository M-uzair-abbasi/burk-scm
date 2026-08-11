from django.contrib import admin

from .models import Shipment, ShipmentEvent


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    can_delete = False
    fields = ("occurred_at", "status", "source")
    readonly_fields = fields


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("tracking_number", "order", "courier", "status", "booked_at", "delivered_at")
    list_filter = ("courier", "status")
    search_fields = ("tracking_number", "order__reference")
    inlines = [ShipmentEventInline]
    readonly_fields = ("order", "courier", "tracking_number", "booked_at")


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "shipment", "status", "source")
    list_filter = ("status", "source")
    readonly_fields = [f.name for f in ShipmentEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
