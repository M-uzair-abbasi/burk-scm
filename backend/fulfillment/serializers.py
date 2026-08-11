from rest_framework import serializers

from logistics.serializers import ShipmentSerializer
from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from orders.models import SalesOrder
from surveillance.serializers import recording_detail

from .models import PackScan, PackingSession
from .services import session_progress


class PackScanSerializer(serializers.ModelSerializer):
    result_display = serializers.CharField(source="get_result_display", read_only=True)
    product_name = serializers.CharField(
        source="product.name", read_only=True, default=None
    )

    class Meta:
        model = PackScan
        fields = (
            "id",
            "barcode",
            "result",
            "result_display",
            "product",
            "product_name",
            "line",
            "manual",
            "scanned_at",
        )
        read_only_fields = fields


class QueueOrderSerializer(serializers.ModelSerializer):
    """An order awaiting packing, for the pack queue."""

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
            "customer_name",
            "item_count",
            "total",
            "placed_at",
            "status",
            "status_display",
        )
        read_only_fields = fields


def session_detail(session: PackingSession) -> dict:
    """Full packing-station payload: the order, per-line scan progress (with each
    line's expected barcode so the client can validate instantly), and the recent
    scan history."""
    prog = session_progress(session)
    lines = []
    for p in prog["lines"]:
        line = p["line"]
        barcode = line.product.barcode if line.product else None
        lines.append(
            {
                "line_id": line.id,
                "sku": line.sku,
                "product_name": line.product_name,
                "barcode": barcode,
                "has_barcode": bool(barcode),
                "required": p["required"],
                "scanned": p["scanned"],
                "complete": p["complete"],
            }
        )
    order = session.order
    return {
        "id": session.id,
        "status": session.status,
        "status_display": session.get_status_display(),
        "complete": prog["complete"],
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "order": {
            "id": order.id,
            "reference": order.reference,
            "channel": order.channel,
            "channel_display": order.get_channel_display(),
            "external_id": order.external_id,
            "customer_name": order.customer_name,
            "status": order.status,
        },
        "lines": lines,
        "recent_scans": PackScanSerializer(
            session.scans.select_related("product").all()[:12], many=True
        ).data,
        "recording": recording_detail(getattr(session, "recording", None)),
        # KPI #2 proof at the station itself: the packaging-video dispatch
        # this session triggered, with each channel's status and latency.
        "video_notifications": NotificationSerializer(
            order.notifications.filter(kind=Notification.Kind.PACKAGING_VIDEO),
            many=True,
        ).data,
        "shipment": ShipmentSerializer(getattr(order, "shipment", None)).data
        if getattr(order, "shipment", None)
        else None,
    }
