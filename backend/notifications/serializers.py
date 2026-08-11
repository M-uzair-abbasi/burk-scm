from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    latency_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "kind_display",
            "channel",
            "channel_display",
            "recipient",
            "status",
            "status_display",
            "reference_event_at",
            "scheduled_for",
            "sent_at",
            "latency_seconds",
            "payload",
            "error",
            "created_at",
        )
        read_only_fields = fields
