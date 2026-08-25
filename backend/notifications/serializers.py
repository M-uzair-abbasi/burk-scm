from urllib.parse import urlsplit

from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    channel_display = serializers.CharField(source="get_channel_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    latency_seconds = serializers.FloatField(read_only=True)
    payload = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()
    terminal_error_class = serializers.SerializerMethodField()

    def _include_operational_errors(self) -> bool:
        if self.context.get("include_operational_errors") is not None:
            return bool(self.context["include_operational_errors"])
        request = self.context.get("request")
        return bool(
            request
            and request.user.is_authenticated
            and request.user.is_manager
        )

    def get_payload(self, obj):
        payload = dict(obj.payload)
        if obj.kind == Notification.Kind.PACKAGING_VIDEO and payload.get("video_url"):
            # Never expose the customer bearer token through staff APIs. The
            # relative endpoint still works for an authorized owner/Manager.
            payload["video_url"] = urlsplit(payload["video_url"]).path
        return payload

    def get_error(self, obj):
        return obj.error if self._include_operational_errors() else ""

    def get_terminal_error_class(self, obj):
        return (
            obj.terminal_error_class if self._include_operational_errors() else ""
        )

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "kind_display",
            "channel",
            "channel_display",
            "idempotency_key",
            "recipient",
            "status",
            "status_display",
            "reference_event_at",
            "scheduled_for",
            "next_attempt_at",
            "sent_at",
            "acknowledged_at",
            "attempt_count",
            "provider_message_id",
            "latency_seconds",
            "payload",
            "error",
            "terminal_error_class",
            "created_at",
        )
        read_only_fields = fields
