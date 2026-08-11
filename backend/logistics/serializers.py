from rest_framework import serializers

from .models import Shipment, ShipmentEvent


class ShipmentEventSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ShipmentEvent
        fields = ("id", "status", "status_display", "occurred_at", "source")
        read_only_fields = fields


class ShipmentSerializer(serializers.ModelSerializer):
    courier_display = serializers.CharField(source="get_courier_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    events = ShipmentEventSerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = (
            "id",
            "courier",
            "courier_display",
            "status",
            "status_display",
            "tracking_number",
            "label_url",
            "booked_at",
            "in_transit_at",
            "delivered_at",
            "events",
        )
        read_only_fields = fields
