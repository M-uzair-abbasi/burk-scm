from rest_framework import serializers

from logistics.serializers import ShipmentSerializer
from notifications.serializers import NotificationSerializer

from .models import SalesOrder, SalesOrderLine, SyncRun


class SalesOrderLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(
        source="product.sku", read_only=True, default=None
    )

    class Meta:
        model = SalesOrderLine
        fields = (
            "id",
            "sku",
            "product",
            "product_sku",
            "product_name",
            "quantity",
            "unit_price",
            "line_total",
        )
        read_only_fields = fields


class SalesOrderListSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SalesOrder
        fields = (
            "id",
            "reference",
            "channel",
            "channel_display",
            "external_id",
            "status",
            "status_display",
            "customer_name",
            "item_count",
            "currency",
            "total",
            "placed_at",
            "ingested_at",
            "last_synced_at",
        )
        read_only_fields = fields


class SalesOrderDetailSerializer(SalesOrderListSerializer):
    lines = SalesOrderLineSerializer(many=True, read_only=True)
    # Module 4/5/6: every dispatch (packaging video, tracking, review reminder)
    # for this order, newest first (Notification.Meta.ordering).
    notifications = NotificationSerializer(many=True, read_only=True)
    # Module 5: null until book_shipment() runs (right after packing). DRF's
    # get_attribute() catches the reverse OneToOne's DoesNotExist and reads as
    # None, so this renders "shipment": null rather than 500ing pre-booking.
    shipment = ShipmentSerializer(read_only=True)

    class Meta(SalesOrderListSerializer.Meta):
        fields = SalesOrderListSerializer.Meta.fields + (
            "customer_phone",
            "customer_email",
            "shipping_address",
            "subtotal",
            "shipping_fee",
            "raw_payload",
            "lines",
            "notifications",
            "shipment",
        )
        read_only_fields = fields


class SyncRunSerializer(serializers.ModelSerializer):
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    reconciled = serializers.BooleanField(read_only=True)

    class Meta:
        model = SyncRun
        fields = (
            "id",
            "channel",
            "channel_display",
            "started_at",
            "finished_at",
            "fetched",
            "created",
            "updated",
            "duplicates_skipped",
            "failed",
            "ok",
            "reconciled",
        )
        read_only_fields = fields
